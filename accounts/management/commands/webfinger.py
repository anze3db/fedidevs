import logging
from json import JSONDecodeError

import httpx
import xml.etree.ElementTree
from asgiref.sync import async_to_sync
from django_rich.management import RichCommand

from accounts.models import Account

logger = logging.getLogger(__name__)


async def get_activitypub_id_from_webfinger(acct, instance, client: httpx.AsyncClient, host_meta_cache):
    if instance not in host_meta_cache:
        try:
            response = await client.get(
                f"https://{instance}/.well-known/host-meta",
                follow_redirects=True, # Should not be required, but who knows
                timeout=30,
            )
        except httpx.HTTPError:
            # Many servers do not implement host-meta and rely on WebFinger's default URL.
            # This is not a failure state.
            pass
        if response is not None and response.status_code == 200:
            try:
                host_meta = xml.etree.ElementTree.fromstring(response.text)
            except xml.etree.ElementTree.ParseError:
                logger.info("%s Error: decoding host-meta XML", acct)
            for element in host_meta or []:
                if element.attrib.get("rel") == "lrdd" and "template" in element.attrib:
                    host_meta_cache[instance] = element.attrib["template"]
                    break
        # If no WebFinger URL is found by now, use the default.
        if instance not in host_meta_cache:
            # The last "{uri}" is intentionally not an f-string, it is needed verbatim.
            host_meta_cache[instance] = f"https://{instance}/.well-known/webfinger?resource=" + "{uri}"
    try:
        response = await client.get(
            host_meta_cache[instance].replace('{uri}', 'acct:' + acct),
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
    result = None
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
    help = "Adds fingerprints to starter pack accounts"

    def handle(self, *args, **options):
        self.main()

    @async_to_sync
    async def main(self):
        accounts_without_fingerprint = Account.objects.filter(activitypub_id__isnull=True).prefetch_related(
            "instance_model"
        )
        async with httpx.AsyncClient() as client:
            # We cache host-meta results per instance in a simple dict because they do not change per account.
            host_meta_cache = {}
            async for account in accounts_without_fingerprint:
                acct = account.get_username_at_instance()
                if acct[0] == "@":
                    acct = acct[1:]
                account.activitypub_id = await get_activitypub_id_from_webfinger(acct, account.instance, client, host_meta_cache)
                if account.activitypub_id:
                    await account.asave(update_fields=["activitypub_id"])
                    # logger.info("%s: ActivityPub ID set", acct)
