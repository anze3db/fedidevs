import asyncio
import datetime as dt
import logging

import httpx
from asgiref.sync import async_to_sync
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils import timezone
from django_rich.management import RichCommand

from accounts.activitypub import (
    actor_home_domain,
    actor_to_account_defaults,
    fetch_actor,
    resolve_actor_url,
)
from accounts.management.commands.instances import process_instances
from accounts.models import Account, Instance

logger = logging.getLogger(__name__)


@async_to_sync
async def crawlone(user: str, make_visible: bool = False) -> Account | None:
    if user.startswith("@"):
        user = user[1:]
    async with httpx.AsyncClient() as client:
        user, instance = user.lower().split("@")
        # The domain in the handle. host-meta may delegate `instance` to another
        # host (e.g. a Brid.gy-bridged personal domain points at fed.brid.gy), but
        # WebFinger still has to be done against the original handle domain.
        handle_domain = instance
        try:
            async_client = httpx.AsyncClient()
            res = await async_client.get(f"https://{instance}/.well-known/host-meta")
            if 300 <= res.status_code < 400:
                logger.info("Redirected to %s", res.headers["Location"])
                instance = res.headers["Location"].split("/")[2]
        except httpx.RequestError:
            logger.info("Error fetching host-meta for %s", instance)

        instance_model = await Instance.objects.filter(instance=instance).afirst()
        if not instance_model:
            await process_instances([instance])
            instance_model = await Instance.objects.filter(instance=instance).afirst()

        account = None
        if instance_model:
            try:
                account = await fetch_user(client, instance, user)
            except Exception as e:
                logger.info(f"Error: {e}")
                account = None

        if not account or not account.get("id"):
            # No usable Mastodon account: the domain has no server, or its account
            # API is absent/gated (e.g. Brid.gy-bridged accounts). Fall back to the
            # account's ActivityPub actor, resolved from the original handle domain.
            return await crawl_via_activitypub(client, handle_domain, user, make_visible)

        last_status_at = None
        if account.get("last_status_at"):
            dt_obj = dt.datetime.fromisoformat(account["last_status_at"])
            if dt_obj.tzinfo:
                last_status_at = dt_obj
            else:
                last_status_at = timezone.make_aware(dt_obj)

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
            "last_status_at": last_status_at,
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


async def crawl_via_activitypub(
    client: httpx.AsyncClient, domain: str, user: str, make_visible: bool = False
) -> Account | None:
    """Add an account by reading its ActivityPub actor instead of the Mastodon API.

    Used when the handle's domain has no Mastodon server (e.g. Brid.gy-bridged
    accounts). The account is stored under the actor's home instance (e.g.
    fed.brid.gy) so it has a non-deleted instance and can be added to packs.
    """
    actor_url = await resolve_actor_url(client, domain, user)
    if not actor_url:
        logger.info("No ActivityPub actor for %s@%s", user, domain)
        return None
    actor = await fetch_actor(client, actor_url)
    if not actor:
        logger.info("Could not fetch ActivityPub actor %s", actor_url)
        return None

    home = actor_home_domain(actor)
    instance_model = await Instance.objects.filter(instance=home).afirst()
    if not instance_model:
        await process_instances([home])
        instance_model = await Instance.objects.filter(instance=home).afirst()
    if not instance_model:
        logger.info("No instance for ActivityPub actor home %s", home)
        return None

    defaults = actor_to_account_defaults(actor, user=user, handle_domain=domain, instance_model=instance_model)
    if make_visible:
        defaults["discoverable"] = True
        defaults["noindex"] = False
    account_obj, created = await Account.objects.aupdate_or_create(
        account_id=actor["id"], instance=instance_model.domain, defaults=defaults
    )
    logger.info("Crawled %s via ActivityPub (created=%s)", defaults["username_at_instance"], created)
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
