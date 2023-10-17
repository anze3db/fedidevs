import asyncio
from datetime import datetime

import httpx
from asgiref.sync import async_to_sync
from django_rich.management import RichCommand

from posts.models import DjangoConUS23Post


class Command(RichCommand):
    help = "Crawles the instance API and saves tag statuses"

    def add_arguments(self, parser):
        ...

    def handle(self, *args, offset=0, instances=None, **options):
        self.main()

    @async_to_sync
    async def main(self):
        async with httpx.AsyncClient() as client:
            instances = [
                "mastodon.social",
                "fosstodon.org",
            ]
            results = await asyncio.gather(
                *[self.fetch(client, instance) for instance in instances]
            )
            for instance, posts in results:
                for result in posts:
                    account = result["account"]

                    await DjangoConUS23Post.objects.aupdate_or_create(
                        post_id=result["id"],
                        instance=account["url"].split("/")[2],
                        defaults={
                            "account": account,
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
                            if result["edited_at"]
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

    async def fetch(self, client, instance: str):
        results = []
        try:
            max_id = "999999999999999999"
            while True:
                self.console.print(f"Fetching {instance} {max_id}")
                response = await client.get(
                    f"https://{instance}/api/v1/timelines/tag/djangocon",
                    params={
                        "q": "",
                        "type": "statuses",
                        "limit": 40,
                        "max_id": max_id,
                    },
                    timeout=30,
                )
                if response.status_code == 429:
                    self.console.print(
                        f"Rate limited, sleeping for 5 minutes {instance}"
                    )
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
