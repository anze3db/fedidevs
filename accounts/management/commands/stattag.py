import asyncio
from datetime import datetime, timezone

import httpx
from asgiref.sync import async_to_sync
from django.utils.timezone import make_aware
from django_rich.management import RichCommand

from confs.models import Fwd50Account, Fwd50Post


class Command(RichCommand):
    help = "Crawles the instance API and saves tag statuses"

    def add_arguments(self, parser):
        parser.add_argument("--tags", type=str, nargs="?", default="")
        parser.add_argument("--instances", type=str, nargs="?", default="")

    def handle(self, *args, tags: str, instances: str, **options):
        self.main(tags=tags, instances=instances)

    @async_to_sync
    async def main(self, tags: str, instances: str):
        tags_lst = tags.split(",")
        instances_lst = instances.split(",")
        async with httpx.AsyncClient() as client:
            for inst in instances_lst:
                instance, posts = await self.fetch(client, tags_lst, inst)
                for result in posts:
                    account = result["account"]

                    if account["url"].split("/")[2] != instance:
                        continue

                    defaults = {
                        "username": account["username"],
                        "acct": account["acct"],
                        "display_name": account["display_name"],
                        "locked": account["locked"],
                        "bot": account["bot"],
                        "discoverable": account.get("discoverable", False),
                        "group": account.get("group", False),
                        "noindex": account.get("noindex", None),
                        "created_at": (datetime.fromisoformat(account["created_at"])),
                        "last_status_at": make_aware(datetime.fromisoformat(account["last_status_at"]))
                        if account["last_status_at"]
                        else None,
                        "last_sync_at": datetime.now(tz=timezone.utc),
                        "followers_count": account["followers_count"],
                        "following_count": account["following_count"],
                        "statuses_count": account["statuses_count"],
                        "note": account["note"],
                        "url": account["url"],
                        "avatar": account["avatar"],
                        "avatar_static": account["avatar_static"],
                        "header": account["header"],
                        "header_static": account["header_static"],
                        "emojis": account["emojis"],
                        "roles": account.get("roles", []),
                        "fields": account["fields"],
                    }
                    account_obj, created = await Fwd50Account.objects.aupdate_or_create(
                        account_id=account["id"],
                        instance=account["url"].split("/")[2],
                        defaults=defaults,
                    )

                    await Fwd50Post.objects.aupdate_or_create(
                        post_id=result["id"],
                        instance=account["url"].split("/")[2],
                        defaults={
                            "account": account_obj,
                            "created_at": datetime.fromisoformat(result["created_at"]),
                            "in_reply_to_id": result["in_reply_to_id"],
                            "in_reply_to_account_id": result["in_reply_to_account_id"],
                            "sensitive": result.get("sensitive", None),
                            "spoiler_text": result["spoiler_text"],
                            "visibility": result["visibility"],
                            "language": result["language"],
                            "uri": result["uri"],
                            "url": result["url"],
                            "replies_count": result["replies_count"],
                            "reblogs_count": result["reblogs_count"],
                            "favourites_count": result["favourites_count"],
                            "edited_at": datetime.fromisoformat(result["edited_at"])
                            if result.get("edited_at")
                            else None,
                            "content": result["content"],
                            "reblog": result["reblog"],
                            "application": result.get("application", None),
                            "media_attachments": result["media_attachments"],
                            "mentions": result["mentions"],
                            "tags": result["tags"],
                            "emojis": result["emojis"],
                            "card": result["card"],
                            "poll": result["poll"],
                        },
                    )

    async def fetch(self, client, tags: list[str], instance: str):
        results = []
        try:
            for tag in tags:
                max_id = "999999999999999999"
                while True:
                    self.console.print(f"Fetching {instance} {max_id}")
                    response = await client.get(
                        f"https://{instance}/api/v1/timelines/tag/{tag}",
                        params={
                            "q": "",
                            "type": "statuses",
                            "limit": 40,
                            "max_id": max_id,
                        },
                        timeout=30,
                    )
                    if response.status_code == 429:
                        self.console.print(f"Rate limited, sleeping for 5 minutes {instance}")
                        await asyncio.sleep(60 * 5)
                        continue
                    if response.status_code != 200:
                        self.console.print(
                            f"[bold red]Error status code[/bold red] for {instance}. {response.status_code}"
                        )
                        return instance, results
                    res = response.json()
                    if not res:
                        break
                    results += res
                    if res[-1]["created_at"] < "2023-01-01 00:00:00.000":
                        break
                    max_id = res[-1]["id"]
                    await asyncio.sleep(5)
        except httpx.HTTPError:
            self.console.print(f"[bold red]Error timeout[/bold red] for {instance}")
            return instance, results

        return instance, results
