import asyncio
from datetime import datetime, timezone

import httpx
from asgiref.sync import async_to_sync
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils.timezone import make_aware
from django_rich.management import RichCommand

from accounts.models import Account

INSTANCES = [
    "chaos.social",
    "cyberplace.social",
    "fosstodon.org",
    "functional.cafe",
    "hachyderm.io",
    "infosec.exchange",
    "mas.to",
    "mastodon.gamedev.place",
    "mastodon.online",
    "mastodon.social",
    "mstdn.social",
    "phpc.social",
    "ruby.social",
    "tech.lgbt",
    "techhub.social",
]


class Command(RichCommand):
    help = "Crawles the fosstodon.org API and saves all accounts to the database"

    def add_arguments(self, parser):
        parser.add_argument("--offset", type=int, nargs="?", default=0)
        parser.add_argument("--instances", type=str, nargs="?", default=None)

    def handle(self, *args, offset=0, instances=None, **options):
        self.main(offset=offset, instances=instances)

    @async_to_sync
    async def main(self, offset: int, instances: str | None):
        async with httpx.AsyncClient() as client:
            start_time = datetime.now(tz=timezone.utc)
            if instances:
                to_index = instances.split(",")
            else:
                to_index = INSTANCES
            while to_index:
                now = datetime.now(tz=timezone.utc)
                results = await asyncio.gather(
                    *[self.fetch(client, offset, instance) for instance in to_index]
                )
                fetched_accounts = []
                for instance, response in results:
                    if not response:
                        self.console.print(f"[green]Done with {instance}[/green]")
                        to_index.remove(instance)
                        continue
                    fetched_accounts += [
                        Account(
                            id=account["id"],
                            username=account["username"],
                            acct=account["acct"],
                            display_name=account["display_name"],
                            locked=account["locked"],
                            bot=account["bot"],
                            discoverable=account["discoverable"],
                            group=account["group"],
                            noindex=account.get("noindex", None),
                            created_at=(datetime.fromisoformat(account["created_at"])),
                            last_status_at=make_aware(
                                datetime.fromisoformat(account["last_status_at"])
                            )
                            if account["last_status_at"]
                            else None,
                            last_sync_at=now,
                            followers_count=account["followers_count"],
                            following_count=account["following_count"],
                            statuses_count=account["statuses_count"],
                            note=account["note"],
                            url=account["url"],
                            avatar=account["avatar"],
                            avatar_static=account["avatar_static"],
                            header=account["header"],
                            header_static=account["header_static"],
                            emojis=account["emojis"],
                            roles=account.get("roles", []),
                            fields=account["fields"],
                        )
                        for account in response
                        if account.get("id")
                    ]
                await Account.objects.abulk_create(
                    fetched_accounts,
                    unique_fields=["id"],
                    update_conflicts=["id"],
                    update_fields=[
                        "username",
                        "acct",
                        "display_name",
                        "locked",
                        "bot",
                        "discoverable",
                        "group",
                        "noindex",
                        "last_status_at",
                        "last_sync_at",
                        "followers_count",
                        "following_count",
                        "statuses_count",
                        "note",
                        "url",
                        "avatar",
                        "avatar_static",
                        "header",
                        "header_static",
                        "emojis",
                        "roles",
                        "fields",
                    ],
                )
                self.console.print(
                    f"Inserted {len(fetched_accounts)}. Current offset {offset}. Started {naturaltime(start_time)}"
                )
                offset += 1

    async def fetch(self, client, offset, instance):
        try:
            response = await client.get(
                f"https://{instance}/api/v1/directory",
                params={
                    "limit": 80,
                    "offset": offset * 80,
                    "local": True,
                    "sort": "active",
                },
                timeout=30,
            )
            return instance, response.json()
        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.RemoteProtocolError,
        ):
            self.console.print(
                f"[bold red]Error timeout[/bold red] for {instance} at offset {offset}"
            )
            return [], instance
