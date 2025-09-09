import asyncio
import datetime as dt
import logging

import httpx
from asgiref.sync import async_to_sync
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils import timezone
from django_rich.management import RichCommand

from accounts.management.commands.instances import process_instances
from accounts.models import Account, Instance

logger = logging.getLogger(__name__)


@async_to_sync
async def crawlone(user: str, make_visible: bool = False) -> Account | None:
    if user.startswith("@"):
        user = user[1:]
    async with httpx.AsyncClient() as client:
        user, instance = user.lower().split("@")
        try:
            async_client = httpx.AsyncClient()
            res = await async_client.get(f"https://{instance}/.well-known/host-meta")
            if 300 <= res.status_code < 400:
                logger.info("Redirected to %s", res.headers["Location"])
                instance = res.headers["Location"].split("/")[2]
        except httpx.RequestError:
            logger.info("Error fetching host-meta for %s", instance)
        try:
            instance_model = await Instance.objects.aget(instance=instance)
        except Instance.DoesNotExist:
            await process_instances([instance])
            instance_model = await Instance.objects.filter(instance=instance).afirst()
            if not instance_model:
                logger.info(f"Instance {instance} not found")
                return
        try:
            account = await fetch_user(client, instance, user)
        except Exception as e:
            logger.info(f"Error: {e}")
            return
        if not account or not account.get("id"):
            logger.info("account not found")
            return
        defaults = {
            "username": account["username"],
            "username_at_instance": f"@{account['username'].lower()}@{instance_model.domain}",
            "instance": account["url"].split("/")[2],
            "instance_model": instance_model,
            "acct": account["acct"],
            "display_name": account["display_name"],
            "locked": account["locked"],
            "bot": account["bot"],
            "discoverable": (account.get("discoverable", False) is True) if not make_visible else True,
            "group": account.get("group", False),
            "noindex": account.get("noindex", None) if not make_visible else False,
            "created_at": (dt.datetime.fromisoformat(account["created_at"])),
            "last_status_at": timezone.make_aware(dt.datetime.fromisoformat(account["last_status_at"]))
            if account.get("last_status_at")
            else None,
            "last_sync_at": timezone.now(),
            "followers_count": account["followers_count"],
            "following_count": account["following_count"],
            "statuses_count": account["statuses_count"],
            "note": account["note"],
            "url": account["url"],
            "activitypub_id": account.get("uri"),
            "avatar": account["avatar"],
            "avatar_static": account["avatar_static"],
            "header": account["header"],
            "header_static": account["header_static"],
            "emojis": account["emojis"],
            "roles": account.get("roles", []),
            "fields": account["fields"],
        }
        account_obj, created = await Account.objects.aupdate_or_create(
            account_id=account["id"],
            instance=account["url"].split("/")[2],
            defaults=defaults,
        )
        logger.info(f"Done, created={created}. Don't forget to run indexer")
        logger.info(
            f"Last status: {naturaltime(defaults['last_status_at'])}, discoverable={defaults['discoverable']}, noindex={defaults['noindex']}"
        )
        if make_visible:
            logger.info("User is now visible")
            if account["noindex"] and account["discoverable"]:
                logger.info(
                    "\n\nHey! Looks like you've opted-out of search engine indexing and that's why you aren't showing up 😔 See the FAQ for instructions on how to fix it: http://fedidevs.com/faq/\n\nI did a manual override so that you show up now, but this is a temporary fix."
                )
            if not account["noindex"] and not account["discoverable"]:
                logger.info(
                    "\n\nHey! Looks like your account is not discoverable and that's why you aren't showing up 😔 See the FAQ for instructions on how to fix it: http://fedidevs.com/faq/\n\nI did a manual override so that you show up now, but this is a temporary fix."
                )
            if account["noindex"] and not account["discoverable"]:
                logger.info(
                    "\n\nHey! Looks like your account is not discoverable and you've opted-out of search engine indexing. That's why you aren't showing up 😔 See the FAQ for instructions on how to fix it: http://fedidevs.com/faq/\n\nI did a manual override so that you show up now, but this is a temporary fix."
                )
        return account_obj


async def fetch_user(client: httpx.AsyncClient, instance: str, user: str, retried=False) -> dict:
    try:
        response = await client.get(
            f"https://{instance}/api/v1/accounts/lookup",
            params={
                "acct": user,
            },
            timeout=30,
            follow_redirects=True,
        )
        if response.status_code == 429:
            if retried:
                logger.warning(f"Rate limit exceeded again for {user}, giving up")
                return {}
            retry_after = response.headers.get("Retry-After", 60)
            logger.info(f"Rate limit exceeded, retrying after {retry_after} seconds")
            await asyncio.sleep(retry_after)
            return await fetch_user(client, instance, user, retried=True)
        elif response.status_code != 200:
            return {}
        return response.json()
    except (
        httpx.ReadTimeout,
        httpx.ConnectTimeout,
        httpx.RemoteProtocolError,
    ):
        logger.info("Error timeout")
        return {}


class Command(RichCommand):
    help = "Crawles the fosstodon.org API and saves all accounts to the database"

    def add_arguments(self, parser):
        parser.add_argument("--user", type=str, nargs="?", default=0)
        parser.add_argument("--make-visible", action="store_true", default=False)

    def handle(self, *args, user: str | None = None, make_visible: bool = False, **options):
        if not user:
            return
        crawlone(user=user, make_visible=make_visible)
