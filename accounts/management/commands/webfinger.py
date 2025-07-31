import logging
from json import JSONDecodeError

import httpx
from asgiref.sync import async_to_sync
from django_rich.management import RichCommand

from accounts.models import Account

logger = logging.getLogger(__name__)


async def get_activitypub_id_from_webfinger(acct, instance, client: httpx.AsyncClient):
    try:
        response = await client.get(
            f"https://{instance}/.well-known/webfinger",
            params={"resource": f"acct:{acct}"},
            follow_redirects=True,  # Required for some servers depending on their setup
            timeout=30,
        )
    except httpx.HTTPError:
        logger.info("%s Error: Failed to fetch WebFinger data", acct)
        return None
    if response.status_code != 200:
        # This hints at a badly misconfigured server or an account that has been deleted.
        # Potentially try again after some delay?
        logger.info("%s Error: status code %s for WebFinger data", acct, response.status_code)
        return None
    try:
        result = response.json()
    except JSONDecodeError:
        logger.info("%s Error: decoding JSON", acct)
        return None
    try:
        # Is this OK style-wise or too crammed?
        for link in result.get("links") or []:
            if link.get("type") == "application/activity+json":
                return link["href"]
        logger.info("%s Error: No ActivityPub link found in WebFinger data %s", acct, result)
        return None
    except:
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
            async for account in accounts_without_fingerprint:
                acct = account.get_username_at_instance()
                if acct[0] == "@":
                    acct = acct[1:]
                account.activitypub_id = await get_activitypub_id_from_webfinger(acct, account.instance, client)
                if account.activitypub_id:
                    await account.asave(update_fields=["activitypub_id"])
                    # logger.info("%s: ActivityPub ID set", acct)
