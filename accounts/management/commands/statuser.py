import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from asgiref.sync import async_to_sync
from django_rich.management import RichCommand

from accounts.models import Account
from posts.models import Post


class Command(RichCommand):
    help = "Crawles the instance API and saves top account statuses"

    def add_arguments(self, parser):
        ...

    def handle(self, *args, offset=0, instances=None, **options):
        min_stat = datetime.now(tz=timezone.utc) - timedelta(days=2)
        accounts = Account.objects.filter(last_status_at__gte=min_stat).order_by(
            "-followers_count"
        )
        self.main(list(accounts))

    @async_to_sync
    async def main(self, accounts: list[Account]):
        async with httpx.AsyncClient() as client:
            # batch by 100 requests
            for i in range(0, len(accounts), 100):
                results = await asyncio.gather(
                    *[self.fetch(client, account) for account in accounts[i : i + 100]]
                )
                for account, posts in results:
                    for result in posts:
                        await Post.objects.aupdate_or_create(
                            post_id=result["id"],
                            account=account,
                            defaults={
                                "created_at": datetime.fromisoformat(
                                    result["created_at"]
                                ),
                                "instance": account.instance,
                                "in_reply_to_id": result["in_reply_to_id"],
                                "in_reply_to_account_id": result[
                                    "in_reply_to_account_id"
                                ],
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
                self.console.print(f"Batch {i//100} done, sleeping for 90s")
                await asyncio.sleep(
                    90
                )  # 300 requests per 5 minute is the default rate limit for Mastodon

    async def fetch(self, client, account: Account):
        try:
            response = await client.get(
                f"https://{account.instance}/api/v1/accounts/{account.account_id}/statuses",
                params={
                    "q": "python",
                    "type": "statuses",
                    "account_id": account.account_id,
                },
                timeout=30,
            )
            if response.status_code == 429:
                self.console.print("Rate limited, sleeping for 5 minutes")
                await asyncio.sleep(60 * 5)
                return await self.fetch(client, account)
            if response.status_code != 200:
                self.console.print(
                    f"[bold red]Error status code[/bold red] for {account}. {response.status_code}"
                )
                return account, []
            return account, response.json()
        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.RemoteProtocolError,
        ):
            self.console.print(f"[bold red]Error timeout[/bold red] for {account}")
            return account, []
