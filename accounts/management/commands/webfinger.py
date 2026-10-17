import logging
from functools import cache
from json import JSONDecodeError

import defusedxml.ElementTree
import httpx
from django.db.models import Q
from django_rich.management import RichCommand

from accounts.models import Account
from mastodon_auth.models import AccountAccess
from starter_packs.models import StarterPackAccount

logger = logging.getLogger(__name__)


@cache
def get_webfinger_url_from_instance_host_meta(instance: str, client: httpx.Client) -> str:
    fallback = f"https://{instance}/.well-known/host-meta?resource=acct:" + "{uri}"

    try:
        response = client.get(
            f"https://{instance}/.well-known/host-meta",
            follow_redirects=True,
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return fallback

    try:
        host_meta = defusedxml.ElementTree.fromstring(response.text)
    except defusedxml.ElementTree.ParseError:
        return fallback

    for element in host_meta:
        if element.attrib.get("rel") == "lrdd" and "template" in element.attrib:
            return element.attrib["template"]

    return fallback


def get_activitypub_id_from_webfinger(acct, instance, client: httpx.Client):
    url = get_webfinger_url_from_instance_host_meta(instance, client)

    try:
        response = client.get(
            url.format(uri=acct),
            follow_redirects=True,  # Required for some servers depending on their setup
            timeout=30,
        )
    except httpx.HTTPError:
        logger.info("%s Error: Failed to fetch WebFinger data", acct)
        return None
    if response.status_code != 200:
        # This hints at a badly misconfigured server or an account that has been deleted.
        logger.info("%s Error: status code %s for WebFinger data", acct, response.status_code)
        return None

    try:
        result = response.json()
    except JSONDecodeError:
        logger.info("%s Error: decoding JSON", acct)
        return None
    try:
        for link in result.get("links") or []:
            if link.get("type") == "application/activity+json":
                return link["href"]
        logger.info("%s Error: No ActivityPub link found in WebFinger data %s", acct, result)
        return None
    except KeyError:
        logger.info("%s Error: Malformed WebFinger data %s", acct, result)
        return None


class Command(RichCommand):
    help = "Adds missing ActivityPub IDs to the accounts and authors of live starter packs"

    def handle(self, *args, **options):
        # Only what share_starter_pack serves over ActivityPub: listed pack members and pack authors.
        member_ids = StarterPackAccount.objects.filter(
            starter_pack__deleted_at__isnull=True,
            account__discoverable=True,
            account__instance_model__isnull=False,
            account__instance_model__deleted_at__isnull=True,
        ).values("account_id")
        author_ids = AccountAccess.objects.filter(user__starterpack__deleted_at__isnull=True).values("account_id")
        accounts_without_fingerprint = (
            Account.objects.filter(activitypub_id__isnull=True)
            .filter(Q(id__in=member_ids) | Q(id__in=author_ids))
            .select_related("instance_model")
            .order_by("id")
        )
        found = 0
        with httpx.Client() as client:
            # Host-meta lookups are cached per instance because they do not change per account.
            for account in accounts_without_fingerprint.iterator():
                acct = account.get_username_at_instance()
                if acct[0] == "@":
                    acct = acct[1:]
                try:
                    activitypub_id = get_activitypub_id_from_webfinger(acct, account.instance, client)
                except Exception:
                    # One bad server must not stop the backfill for everyone after it.
                    logger.exception("%s Error: WebFinger lookup failed", acct)
                    continue
                if activitypub_id:
                    account.activitypub_id = activitypub_id
                    account.save(update_fields=["activitypub_id"])
                    found += 1
        logger.info("Added ActivityPub IDs to %d accounts", found)
