import asyncio
import datetime as dt
import logging
from json import JSONDecodeError

import httpx
from asgiref.sync import async_to_sync
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db import ProgrammingError
from django.utils import timezone
from django_rich.management import RichCommand

from accounts.models import Account, Instance

logger = logging.getLogger(__name__)


def convert_last_status_at(last_status_at: str | None) -> dt.datetime | None:
    if not last_status_at:
        return None
    try:
        return timezone.make_aware(dt.datetime.fromisoformat(last_status_at))
    except ValueError:
        return dt.datetime.fromisoformat(last_status_at)


class Command(RichCommand):
    help = "Crawles the fosstodon.org API and saves all accounts to the database"

    def add_arguments(self, parser):
        parser.add_argument("--offset", type=int, nargs="?", default=0)
        parser.add_argument("--instances", type=str, nargs="?", default=None)
        parser.add_argument("--skip-inactive-for", type=int, nargs="?", default=3)

    def handle(
        self,
        *args,
        offset=0,
        instances=None,
        skip_inactive_for: int = 3,
        **options,
    ):
        self.main(
            offset=offset,
            instances=instances,
            skip_inactive_for=skip_inactive_for,
        )

    @async_to_sync
    async def main(
        self,
        offset: int,
        instances: str | None,
        skip_inactive_for: int = 0,
    ):
        async with httpx.AsyncClient() as client:
            start_time = timezone.now()
            instance_models = await Instance.objects.ain_bulk(field_name="instance")
            if instances:
                all_to_index = instances.split(",")
            else:
                all_to_index = [
                    i async for i in Instance.objects.filter(deleted_at__isnull=True).values_list("instance", flat=True)
                ]
            original_offset = offset
            for batch in range(0, len(all_to_index), 50):
                self.console.print(f"{batch / len(all_to_index) * 100:.2f}% completed")
                offset = original_offset
                to_index = all_to_index[batch : batch + 50]
                while to_index:
                    now = timezone.now()
                    results = await asyncio.gather(
                        *[self.fetch(client, offset, instance, skip_inactive_for) for instance in to_index]
                    )
                    fetched_accounts = []
                    for instance, response in results:
                        if not response:
                            self.console.print(f"[green]Done with {instance}[/green]")
                            to_index.remove(instance)
                            continue
                        inst = instance_models.get(instance)
                        fetched_accounts += [
                            Account(
                                account_id=account["id"],
                                instance=account["url"].split("/")[2],
                                instance_model=inst,
                                username=account["username"],
                                username_at_instance=f"@{account['username'].lower()}@{inst.domain.lower()}",
                                acct=account["acct"],
                                display_name=account["display_name"],
                                locked=account["locked"],
                                bot=account["bot"],
                                discoverable=account.get("discoverable", False),
                                group=account.get("group", False),
                                noindex=account.get("noindex", None),
                                created_at=(dt.datetime.fromisoformat(account["created_at"])),
                                last_status_at=convert_last_status_at(account.get("last_status_at")),
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
                    inserted_accounts = fetched_accounts
                    try:
                        await Account.objects.abulk_create(
                            inserted_accounts,
                            unique_fields=["account_id", "instance"],
                            update_conflicts=["account_id", "instance"],
                            update_fields=[
                                "username",
                                "username_at_instance",
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
                                "instance_model",
                            ],
                        )
                    except ProgrammingError:
                        logger.warning(
                            "Faled to insert",
                            extra={
                                "inserted_accounts": [
                                    f"{account.instance} {account.account_id}" for account in inserted_accounts
                                ]
                            },
                        )
                        inserted_accounts = []
                    if fetched_accounts:
                        self.console.print(
                            f"Fetched {len(fetched_accounts)}, inserted {len(inserted_accounts)}. Current offset {offset}. Max last_status_at {naturaltime(max(account.last_status_at for account in fetched_accounts if account.last_status_at))}"
                        )
                    offset += 1
            self.console.print(
                f"Done. Started at {start_time}. Ended at {timezone.now()}, duration {timezone.now() - start_time}"
            )

    async def fetch(self, client, offset, instance, skip_inactive_for: int):
        if offset > 100:
            return instance, []
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
        except httpx.HTTPError:
            self.console.print(f"[bold red]Error timeout[/bold red] for {instance} at offset {offset}")
            return instance, []
        except Exception as e:
            self.console.print(f"[bold red]Error[/bold red] for {instance} at offset {offset}", e)
            return instance, []

        if response.status_code != 200:
            self.console.print(
                f"[bold red]Error status code[/bold red] for {instance} at offset {offset}. {response.status_code}"
            )
            return instance, []
        try:
            results = response.json()
        except JSONDecodeError:
            logger.info("Error decoding JSON", extra={"response": response.text})
            return instance, []

        # Don't skip inactive accounts if skip_inactive_for is None or 0
        if not skip_inactive_for:
            return instance, results

        def is_recently_updated(account) -> bool:
            if not account.get("last_status_at"):
                return False
            try:
                last_status_at = timezone.make_aware(dt.datetime.fromisoformat(account["last_status_at"]))
            except ValueError:
                last_status_at = dt.datetime.fromisoformat(account["last_status_at"])
            if (timezone.now() - last_status_at) > dt.timedelta(days=skip_inactive_for):
                return False
            return True

        results = [r for r in results if is_recently_updated(r)]
        return instance, results
