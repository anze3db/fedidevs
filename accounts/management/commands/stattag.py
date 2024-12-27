import asyncio
import datetime as dt
import logging

import httpx
from asgiref.sync import async_to_sync
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django_rich.management import RichCommand

from accounts.management.commands.instances import process_instances
from accounts.models import Account, Instance
from confs.models import Conference, ConferenceAccount, ConferencePost, MinId
from posts.models import Post

logger = logging.getLogger(__name__)


class Command(RichCommand):
    help = "Crawles the instance API and saves tag statuses"

    def add_arguments(self, parser):
        parser.add_argument("--slug", type=str, nargs="?", default="")
        parser.add_argument(
            "--active",
            action="store_true",
        )

    def handle(self, *args, slug: str, active: bool, **options):
        self.main(slug=slug, active=active)

    @async_to_sync
    async def main(self, slug: str, active: bool):
        if slug:
            conferences = [await Conference.objects.aget(slug=slug)]
        elif active:
            conferences = [
                c async for c in Conference.objects.filter(start_date__lte=timezone.now(), end_date__gte=timezone.now())
            ]
        else:
            conferences = [c async for c in Conference.objects.filter(archived_date__isnull=True)]

        for conference in conferences:
            if not conference.instances:
                self.console.log(f"No instances for {conference.slug}")
            instances = conference.instances.split(",")
            await asyncio.gather(*[self.handle_instance(instance.strip(), conference) for instance in instances])

    async def handle_instance(self, instance, conference):
        self.console.print(f"Starting {instance}, {conference.slug}")

        try:
            instance_model = await Instance.objects.aget(instance=instance)
        except Instance.DoesNotExist:
            await process_instances([instance])
            instance_model = await Instance.objects.filter(instance=instance).afirst()
            if instance_model is None:
                logger.warning("Instance %s not found", instance)

        tags = list({tag.strip().replace("#", "").lower() for tag in conference.tags.split(",") if conference.tags})
        min_ids = MinId.objects.filter(conference=conference, instance=instance)
        min_id = min([min_id.min_id async for min_id in min_ids], default="111054552104295026")
        min_id_to_save = min_id
        for tag in tags:
            async with httpx.AsyncClient() as client:
                while True:
                    posts = await self.fetch_and_handle_fail(client, instance, tag, min_id)
                    if not posts:
                        break
                    if min_id == posts[-1]["id"]:
                        break
                    min_id = posts[-1]["id"]
                    if dt.datetime.fromisoformat(posts[-1]["created_at"]) < (timezone.now() - dt.timedelta(days=1)):
                        min_id_to_save = min_id
                    await self.process_posts(posts, conference, instance_model)

        min_ids = []
        min_ids.append(MinId(conference=conference, instance=instance, min_id=min_id_to_save))

        await MinId.objects.abulk_create(
            min_ids, update_conflicts=True, unique_fields=["conference", "instance"], update_fields=["min_id"]
        )

    async def fetch_and_handle_fail(self, client, instance: str, tag: str, min_id: str):
        try:
            response = await client.get(
                f"https://{instance}/api/v1/timelines/tag/{tag}",
                params={
                    "q": "",
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
                return await self.fetch_and_handle_fail(client, instance, tag, min_id)
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

    async def process_posts(self, posts, conference, instance_model):
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
                    "created_at": (dt.datetime.fromisoformat(account["created_at"])),
                    "last_status_at": timezone.make_aware(dt.datetime.fromisoformat(account["last_status_at"]))
                    if account.get("last_status_at")
                    else None,
                    "last_sync_at": timezone.now(),
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
                    "instance_model": instance_model,
                }
            )
            for account in unique_accounts
        ]
        accounts = await Account.objects.abulk_create(
            accounts,
            update_conflicts=True,
            update_fields=["last_sync_at", "followers_count", "following_count", "statuses_count", "instance_model"],
            unique_fields=["account_id", "instance"],
        )
        account_map = {account.url: account for account in accounts}

        post_objs = [
            Post(
                **{
                    "post_id": result["id"],
                    "account": account_map[result["account"]["url"]],
                    "instance": result["account"]["url"].split("/")[2],
                    "created_at": dt.datetime.fromisoformat(result["created_at"]),
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
                    "edited_at": dt.datetime.fromisoformat(result["edited_at"]) if result.get("edited_at") else None,
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
        await asyncio.gather(
            conference.posts.aadd(*post_objs),
            conference.accounts.aadd(*[post.account for post in post_objs]),
        )

        if conference.posts_after:
            posts_after = conference.posts_after
        else:
            posts_after = timezone.now() - dt.timedelta(days=999)

        await ConferenceAccount.objects.filter(conference=conference).aupdate(
            count=Coalesce(
                Subquery(
                    conference.posts.values("account_id")
                    .filter(account_id=OuterRef("account_id"), created_at__gte=posts_after)
                    .annotate(post_count=Count("id"))
                    .values("post_count")[:1],
                ),
                Value(0),
            )
        )

        await ConferencePost.objects.filter(conference=conference).aupdate(
            created_at=Subquery(Post.objects.filter(id=OuterRef("post_id")).values("created_at")[:1]),
            favourites_count=Subquery(Post.objects.filter(id=OuterRef("post_id")).values("favourites_count")[:1]),
            reblogs_count=Subquery(Post.objects.filter(id=OuterRef("post_id")).values("reblogs_count")[:1]),
            replies_count=Subquery(Post.objects.filter(id=OuterRef("post_id")).values("replies_count")[:1]),
            visibility=Subquery(Post.objects.filter(id=OuterRef("post_id")).values("visibility")[:1]),
            account_id=Subquery(Post.objects.filter(id=OuterRef("post_id")).values("account_id")[:1]),
        )
