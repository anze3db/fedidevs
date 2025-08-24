import asyncio
import logging
from datetime import datetime, timedelta

import httpx
from asgiref.sync import async_to_sync
from django_rich.management import RichCommand

from confs.models import Conference


class Command(RichCommand):
    help = "Get instances that tooted about a particular tag"

    def add_arguments(self, parser):
        parser.add_argument("--slug", type=str, nargs="?", default="")

    def handle(self, slug: str = "", *args, **options):
        self.main(slug)

    @async_to_sync
    async def main(self, slug: str = ""):
        async with httpx.AsyncClient() as client:
            if slug:
                conferences = Conference.objects.filter(slug=slug)
            else:
                conferences = Conference.objects.all()

            async for conference in conferences:
                tags = [tag.strip().replace("#", "") for tag in conference.tags.split(",")]
                posts = await self.fetch_and_handle_fail(client, "mastodon.social", list(tags))
                if not posts:
                    continue
                last_post_date = datetime.fromisoformat(posts[-1]["created_at"])
                first_post_date = datetime.fromisoformat(posts[0]["created_at"])
                if (first_post_date - last_post_date) < timedelta(days=1):
                    logging.info(
                        "Might have missed some instances for %s, %s",
                        conference.name,
                        first_post_date - last_post_date,
                    )

                instances = {post.get("account", {}).get("url", "").split("/")[2] for post in posts}
                existing_instances = {inst.strip() for inst in conference.instances.split(",")}
                verified_instances = set()
                for instance in instances.difference(existing_instances):
                    posts = await self.fetch_and_handle_fail(client, instance, list(tags))
                    if not posts:
                        self.console.print(f"[red]Failed[/red] {instance}")
                        # TODO: Add to ignored instances
                        continue
                    self.console.print(f"[green]Verified[/green] {instance}")
                    verified_instances.add(instance)
                if not verified_instances:
                    continue
                self.console.log("Adding", conference.name, verified_instances)
                conference.instances = ", ".join(existing_instances.union(verified_instances))
                await conference.asave()

    async def fetch_and_handle_fail(self, client, instance: str, tags: list[str]):
        try:
            # self.console.print(f"Fetching {instance} {f"https://{instance}/api/v1/timelines/tag/{tags}"}")
            response = await client.get(
                f"https://{instance}/api/v1/timelines/tag/{tags[0]}",
                params={
                    "q": "",
                    "any": tags[1:],
                    "type": "statuses",
                    "limit": 40,
                    # "min_id": min_id,
                    "local": False,
                },
                timeout=3,
            )
            if response.status_code == 429:
                self.console.print(f"Rate limited, sleeping for 5 minutes {instance}")
                await asyncio.sleep(60 * 5)
                return await self.fetch_and_handle_fail(client, instance, tags)
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
