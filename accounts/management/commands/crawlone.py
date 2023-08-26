from datetime import datetime, timezone

import httpx
from asgiref.sync import async_to_sync
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils.timezone import make_aware
from django_rich.management import RichCommand

from accounts.models import Account


class Command(RichCommand):
    help = "Crawles the fosstodon.org API and saves all accounts to the database"

    def add_arguments(self, parser):
        parser.add_argument("--user", type=str, nargs="?", default=0)
        parser.add_argument("--make-visible", action="store_true", default=False)

    def handle(
        self, *args, user: str | None = None, make_visible: bool = False, **options
    ):
        if not user:
            return
        self.main(user=user, make_visible=make_visible)

    @async_to_sync
    async def main(self, user: str, make_visible: bool = False):
        async with httpx.AsyncClient() as client:
            user, instance = user.split("@")
            user_id = await self.fetch_id(client, instance, user)
            if not user_id:
                self.console.print("id not found")
                return
            account = await self.fetch_user(client, instance, user_id)
            if not account or not account.get("id"):
                self.console.print("account not found")
                return
            defaults = dict(
                username=account["username"],
                acct=account["acct"],
                display_name=account["display_name"],
                locked=account["locked"],
                bot=account["bot"],
                discoverable=account.get("discoverable", False)
                if not make_visible
                else True,
                group=account.get("group", False),
                noindex=account.get("noindex", None) if not make_visible else False,
                created_at=(datetime.fromisoformat(account["created_at"])),
                last_status_at=make_aware(
                    datetime.fromisoformat(account["last_status_at"])
                )
                if account["last_status_at"]
                else None,
                last_sync_at=datetime.now(tz=timezone.utc),
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
            _, created = await Account.objects.aupdate_or_create(
                account_id=account["id"],
                instance=account["url"].split("/")[2],
                defaults=defaults,
            )
            self.console.print(f"Done, created={created}. Don't forget to run indexer")
            self.console.print(
                f"Last status: {naturaltime(defaults['last_status_at'])}, discoverable={defaults['discoverable']}, noindex={defaults['noindex']}"
            )
            if make_visible:
                self.console.print("User is now visible")
                if account["noindex"] and account["discoverable"]:
                    self.console.print(
                        "\n\nHey! Looks like you’ve opted-out of search engine indexing and that's why you aren't showing up 😔 See the FAQ for instructions on how to fix it: http://fedidevs.com/faq/\n\nI did a manual override so that you show up now, but this is a temporary fix."
                    )
                if not account["noindex"] and not account["discoverable"]:
                    self.console.print(
                        "\n\nHey! Looks like your account is not discoverable and that's why you aren't showing up 😔 See the FAQ for instructions on how to fix it: http://fedidevs.com/faq/\n\nI did a manual override so that you show up now, but this is a temporary fix."
                    )
                if account["noindex"] and not account["discoverable"]:
                    self.console.print(
                        "\n\nHey! Looks like your account is not discoverable and you've opted-out of search engine indexing. That's why you aren't showing up 😔 See the FAQ for instructions on how to fix it: http://fedidevs.com/faq/\n\nI did a manual override so that you show up now, but this is a temporary fix."
                    )

    async def fetch_id(self, client, instance: str, user: str) -> str:
        try:
            response = await client.get(
                f"https://{instance}/api/v1/accounts/lookup",
                params={
                    "acct": user,
                },
                timeout=30,
            )
            if response.status_code != 200:
                self.console.print(
                    f"[bold red]Error status code[/bold red]. {response.status_code}"
                )
                return None
            return response.json().get("id")
        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.RemoteProtocolError,
        ):
            self.console.print(f"[bold red]Error timeout[/bold red]")
            return None

    async def fetch_user(self, client, instance: str, user_id: str):
        try:
            response = await client.get(
                f"https://{instance}/api/v1/accounts/{user_id}",
                timeout=30,
            )
            if response.status_code != 200:
                self.console.print(
                    f"[bold red]Error status code[/bold red]. {response.status_code}"
                )
                return None
            return response.json()
        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.RemoteProtocolError,
        ):
            self.console.print("[bold red]Error timeout[/bold red]")
            return None
