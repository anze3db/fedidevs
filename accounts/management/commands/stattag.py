import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from asgiref.sync import async_to_sync
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils.timezone import make_aware
from django_rich.management import RichCommand

from accounts.models import Account
from confs.models import Conference, ConferenceAccount, MinId
from posts.models import Post


class Command(RichCommand):
    help = "Crawles the instance API and saves tag statuses"

    def add_arguments(self, parser):
        parser.add_argument("--slug", type=str, nargs="?", default="")

    def handle(self, *args, slug: str, **options):
        self.main(slug=slug)

    @async_to_sync
    async def main(self, slug: str):
        if slug:
            conferences = [await Conference.objects.aget(slug=slug)]
        else:
            conferences = [c async for c in Conference.objects.filter(archived_date__isnull=True)]

        instances_lst = {
            instance.strip()
            for conference in conferences
            for instance in conference.instances.split(",")
            if conference.instances and instance.strip()
        }
        await asyncio.gather(
            *[
                self.handle_instance(instance, [c for c in conferences if instance in c.instances])
                for instance in instances_lst
            ]
        )

    async def handle_instance(self, instance, conferences):
        tags = list(
            {
                tag.strip().replace("#", "").lower()
                for conference in conferences
                for tag in conference.tags.split(",")
                if conference.tags
            }
        )
        min_ids = MinId.objects.filter(conference__in=conferences, instance=instance)
        min_id = min([min_id.min_id async for min_id in min_ids], default="111054552104295026")
        min_id_to_save = min_id
        async with httpx.AsyncClient() as client:
            while True:
                posts = await self.fetch_and_handle_fail(client, instance, tags, min_id)
                if not posts:
                    break
                min_id = posts[-1]["id"]
                if datetime.fromisoformat(posts[-1]["created_at"]) < (
                    datetime.now(tz=timezone.utc) - timedelta(days=3)
                ):
                    min_id_to_save = min_id
                await self.process_posts(posts, conferences)

        min_ids = []
        for conf in conferences:
            min_ids.append(MinId(conference=conf, instance=instance, min_id=min_id_to_save))

        await MinId.objects.abulk_create(
            min_ids, update_conflicts=True, unique_fields=["conference", "instance"], update_fields=["min_id"]
        )

    async def fetch_and_handle_fail(self, client, instance: str, tags: list[str], min_id: str):
        try:
            response = await client.get(
                f"https://{instance}/api/v1/timelines/tag/{tags[0]}",
                params={
                    "q": "",
                    "any": tags[1:],
                    "type": "statuses",
                    "limit": 40,
                    "min_id": min_id,
                    "local": True,
                },
                timeout=30,
            )
            if response.status_code == 429:
                self.console.print(f"Rate limited, sleeping for 5 minutes {instance}")
                await asyncio.sleep(60 * 5)
                return await self.fetch_and_handle_fail(client, instance, tags, min_id)
            if response.status_code != 200:
                self.console.print(f"[bold red]Error status code[/bold red] for {instance}. {response.status_code}")
                return []
            return response.json()
        except httpx.HTTPError:
            self.console.print(f"[bold red]Error Http[/bold red] for {instance}")
            return []
        except Exception as e:
            self.console.print(f"[bold red]Error Unknown[/bold red] for {instance}", e)
            return []

    async def process_posts(self, posts, conferences):
        unique_accounts = []
        seen_account_ids = set()
        for post in posts:
            if post["account"]["id"] not in seen_account_ids:
                seen_account_ids.add(post["account"]["id"])
                unique_accounts.append(post["account"])

        accounts = [
            Account(
                **{
                    "url": account["url"],
                    "account_id": account["id"],
                    "instance": account["url"].split("/")[2],
                    "username": account["username"],
                    "acct": account["acct"],
                    "display_name": account["display_name"],
                    "locked": account["locked"],
                    "bot": account["bot"],
                    "discoverable": account.get("discoverable", False) or False,
                    "group": account.get("group", False),
                    "noindex": account.get("noindex", None),
                    "created_at": (datetime.fromisoformat(account["created_at"])),
                    "last_status_at": make_aware(datetime.fromisoformat(account["last_status_at"]))
                    if account.get("last_status_at")
                    else None,
                    "last_sync_at": datetime.now(tz=timezone.utc),
                    "followers_count": account["followers_count"],
                    "following_count": account["following_count"],
                    "statuses_count": account["statuses_count"],
                    "note": account["note"],
                    "avatar": account["avatar"],
                    "avatar_static": account["avatar_static"],
                    "header": account["header"],
                    "header_static": account["header_static"],
                    "emojis": account["emojis"],
                    "roles": account.get("roles", []),
                    "fields": account["fields"],
                }
            )
            for account in unique_accounts
        ]
        accounts = await Account.objects.abulk_create(
            accounts,
            update_conflicts=True,
            update_fields=["last_sync_at", "followers_count", "following_count", "statuses_count"],
            unique_fields=["account_id", "instance"],
        )
        account_map = {account.url: account for account in accounts}

        post_objs = [
            Post(
                **{
                    "post_id": result["id"],
                    "account": account_map[result["account"]["url"]],
                    "instance": result["account"]["url"].split("/")[2],
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
                    "edited_at": datetime.fromisoformat(result["edited_at"]) if result.get("edited_at") else None,
                    "content": result["content"],
                    "reblog": result["reblog"],
                    "application": result.get("application", None),
                    "media_attachments": result["media_attachments"],
                    "mentions": result["mentions"],
                    "tags": result["tags"],
                    "emojis": result["emojis"],
                    "card": result["card"],
                    "poll": result["poll"],
                }
            )
            for result in posts
        ]
        post_objs = await Post.objects.abulk_create(
            post_objs,
            update_conflicts=True,
            update_fields=["replies_count", "reblogs_count", "favourites_count"],
            unique_fields=["post_id", "account"],
        )

        for conf in conferences:
            conf_tags = [c.strip().replace("#", "").lower() for c in conf.tags.split(",")]
            posts = []
            for post in post_objs:
                for tag in post.tags:
                    if tag["name"].lower() in conf_tags:
                        posts.append(post)
                        break
            await asyncio.gather(
                conf.posts.aadd(*posts),
                conf.accounts.aadd(*[post.account for post in posts]),
            )

            if conf.posts_after:
                posts_after = conf.posts_after
            else:
                posts_after = datetime.now(tz=timezone.utc) - timedelta(days=999)

            await ConferenceAccount.objects.filter(conference=conf).aupdate(
                count=Coalesce(
                    Subquery(
                        conf.posts.values("account_id")
                        .filter(account_id=OuterRef("account_id"), created_at__gte=posts_after)
                        .annotate(post_count=Count("id"))
                        .values("post_count")[:1],
                    ),
                    Value(0),
                )
            )
