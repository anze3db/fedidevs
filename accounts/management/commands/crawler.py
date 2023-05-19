import asyncio
from datetime import datetime, timezone

import httpx
from asgiref.sync import async_to_sync
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils.timezone import make_aware
from django_rich.management import RichCommand

from accounts.models import Account

INSTANCES = [
    "c.im",
    "chaos.social",
    "cyberplace.social",
    "dotnet.social",
    "floss.social",
    "fosstodon.org",
    "functional.cafe",
    "hachyderm.io",
    "indieweb.social",
    "infosec.exchange",
    "mas.to",
    "masto.ai",
    "mastodon.cloud",
    "mastodon.gamedev.place",
    "mastodon.online",
    "mastodon.social",
    "mastodon.world",
    "mastodonapp.uk",
    "mozilla.social",
    "mstdn.party",
    "mstdn.social",
    "ohai.social",
    "oldbytes.space",
    "phpc.social",
    "ruby.social",
    "sfba.social",
    "social.juanlu.space",
    "tech.lgbt",
    "techhub.social",
    "universeodon.com",
    # "masto.ai"
    # "social.kernel.org",
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
                            account_id=account["id"],
                            instance=account["url"].split("/")[2],
                            username=account["username"],
                            acct=account["acct"],
                            display_name=account["display_name"],
                            locked=account["locked"],
                            bot=account["bot"],
                            discoverable=account.get("discoverable", False),
                            group=account.get("group", False),
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
                    unique_fields=["account_id", "instance"],
                    update_conflicts=["account_id", "instance"],
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
            self.console.print("Disabling accounts that are not discoverable anymore")
            # TODO: Maybe I should fetch the most recent data from the instances instead?
            # Account.objects.filter(last_sync_at__lt=start_time).update(
            #     discoverable=False
            # )

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
            if response.status_code != 200:
                self.console.print(
                    f"[bold red]Error status code[/bold red] for {instance} at offset {offset}. {response.status_code}"
                )
                return instance, []
            return instance, response.json()
        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.RemoteProtocolError,
        ):
            self.console.print(
                f"[bold red]Error timeout[/bold red] for {instance} at offset {offset}"
            )
            return instance, []
