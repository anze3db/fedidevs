import asyncio
from datetime import datetime, timedelta, timezone

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
        parser.add_argument("--skip-inactive-for", type=int, nargs="?", default=90)

    def handle(
        self, *args, offset=0, instances=None, skip_inactive_for: int = 0, **options
    ):
        self.main(
            offset=offset, instances=instances, skip_inactive_for=skip_inactive_for
        )

    @async_to_sync
    async def main(
        self, offset: int, instances: str | None, skip_inactive_for: int = 0
    ):
        async with httpx.AsyncClient() as client:
            start_time = datetime.now(tz=timezone.utc)
            if instances:
                to_index = instances.split(",")
            else:
                to_index = INSTANCES
            while to_index:
                now = datetime.now(tz=timezone.utc)
                results = await asyncio.gather(
                    *[
                        self.fetch(client, offset, instance, skip_inactive_for)
                        for instance in to_index
                    ]
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
                if fetched_accounts:
                    self.console.print(
                        f"Inserted {len(fetched_accounts)}. Current offset {offset}. Max last_status_at {naturaltime(max(account.last_status_at for account in fetched_accounts if account.last_status_at))}"
                    )
                offset += 1
            self.console.print(
                f"Done. Started at {start_time}. Ended at {datetime.now(tz=timezone.utc)}, duration {datetime.now(tz=timezone.utc) - start_time}"
            )

    async def fetch(self, client, offset, instance, skip_inactive_for: int):
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
            results = response.json()

            # Don't skip inactive accounts if skip_inactive_for is None or 0
            if not skip_inactive_for:
                return instance, results

            def is_recently_updated(account) -> bool:
                if not account.get("last_status_at"):
                    return False
                last_status_at = make_aware(
                    datetime.fromisoformat(account["last_status_at"])
                )
                if (datetime.now(tz=timezone.utc) - last_status_at) > timedelta(
                    days=skip_inactive_for
                ):
                    return False
                return True

            before = len(results)
            results = [r for r in results if is_recently_updated(r)]
            after = len(results)
            if before != after:
                self.console.print(
                    f"[bold yellow]Filtered out {before - after} accounts[/bold yellow] for {instance} at offset {offset}"
                )
            return instance, results
        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.RemoteProtocolError,
        ):
            self.console.print(
                f"[bold red]Error timeout[/bold red] for {instance} at offset {offset}"
            )
            return instance, []
