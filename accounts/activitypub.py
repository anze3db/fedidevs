"""Minimal ActivityPub actor lookup, used as a fallback when an account can't be
fetched through the Mastodon client API.

Some fediverse software either has no Mastodon API at all (e.g. Brid.gy-bridged
accounts, whose handle domain is a personal site) or gates the account endpoints
behind auth (e.g. GoToSocial). For those we resolve the account's ActivityPub
actor via WebFinger and read the public actor document directly.

Note: servers in "authorized fetch"/secure mode require HTTP-signed requests even
for the actor document, so those still won't resolve here without request signing.
"""

import datetime as dt
import logging
from urllib.parse import urlsplit

import httpx
from django.utils import timezone

logger = logging.getLogger(__name__)

_AP_ACCEPT = 'application/activity+json, application/ld+json; profile="https://www.w3.org/ns/activitystreams"'
_TIMEOUT = 15


async def resolve_actor_url(client: httpx.AsyncClient, domain: str, user: str) -> str | None:
    """WebFinger ``acct:user@domain`` -> the actor's ActivityPub id (self link)."""
    try:
        res = await client.get(
            f"https://{domain}/.well-known/webfinger",
            params={"resource": f"acct:{user}@{domain}"},
            headers={"Accept": "application/jrd+json"},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        logger.info("WebFinger failed for %s@%s", user, domain)
        return None
    if res.status_code != 200:
        return None
    try:
        links = res.json().get("links", [])
    except ValueError:
        return None
    for link in links:
        if link.get("rel") == "self" and "activity+json" in (link.get("type") or "") and link.get("href"):
            return link["href"]
    return None


async def fetch_actor(client: httpx.AsyncClient, actor_url: str) -> dict | None:
    """Fetch and return an ActivityPub actor document, or None.

    Returns None on non-200 (incl. the 401 returned by secure-mode servers that
    require a signed request) or unparseable bodies.
    """
    try:
        res = await client.get(actor_url, headers={"Accept": _AP_ACCEPT}, timeout=_TIMEOUT, follow_redirects=True)
    except httpx.HTTPError:
        logger.info("ActivityPub actor fetch failed for %s", actor_url)
        return None
    if res.status_code != 200:
        logger.info("ActivityPub actor %s returned %s", actor_url, res.status_code)
        return None
    try:
        actor = res.json()
    except ValueError:
        return None
    if not isinstance(actor, dict) or not actor.get("id"):
        return None
    return actor


def actor_home_domain(actor: dict) -> str:
    """The host that serves the actor (e.g. fed.brid.gy for a bridged account)."""
    return urlsplit(actor["id"]).netloc


def _media_url(value) -> str:
    """An AP icon/image may be a dict, a list of dicts, or a plain URL string."""
    if isinstance(value, dict):
        return value.get("url") or ""
    if isinstance(value, list) and value:
        first = value[0]
        return (first.get("url") if isinstance(first, dict) else first) or ""
    if isinstance(value, str):
        return value
    return ""


def _profile_url(actor: dict) -> str:
    """AP ``url`` may be a string, a Link object, or a list of either."""
    url = actor.get("url")
    if isinstance(url, str):
        return url
    candidates = url if isinstance(url, list) else [url]
    for candidate in candidates:
        if isinstance(candidate, str):
            return candidate
        if isinstance(candidate, dict) and candidate.get("href"):
            return candidate["href"]
    return actor["id"]


def actor_to_account_defaults(actor: dict, *, user: str, handle_domain: str, instance_model) -> dict:
    """Map an ActivityPub actor to ``Account.objects.update_or_create`` defaults.

    `handle_domain` is the domain the user searched (used for the displayed
    handle); `instance_model` is the indexable home instance the account is stored
    under. AP actors don't expose follower/post counts, so those default to 0.
    """
    username = actor.get("preferredUsername") or user
    actor_type = actor.get("type")

    created_at = timezone.now()
    if published := actor.get("published"):
        try:
            parsed = dt.datetime.fromisoformat(published.replace("Z", "+00:00"))
            created_at = parsed if parsed.tzinfo else timezone.make_aware(parsed)
        except ValueError, TypeError:
            pass

    icon = _media_url(actor.get("icon"))
    image = _media_url(actor.get("image"))
    return {
        "username": username,
        "username_at_instance": f"@{username}@{handle_domain}".lower(),
        "instance": instance_model.domain,
        "instance_model": instance_model,
        "acct": f"{username}@{handle_domain}",
        "display_name": actor.get("name") or username,
        "locked": bool(actor.get("manuallyApprovesFollowers", False)),
        "bot": actor_type in ("Service", "Application"),
        "discoverable": actor.get("discoverable", False) is True,
        "group": actor_type == "Group",
        "noindex": None,
        "created_at": created_at,
        "last_status_at": None,
        "last_sync_at": timezone.now(),
        "followers_count": 0,
        "following_count": 0,
        "statuses_count": 0,
        "note": actor.get("summary") or "",
        "url": _profile_url(actor),
        "activitypub_id": actor["id"],
        "avatar": icon,
        "avatar_static": icon,
        "header": image,
        "header_static": image,
        "emojis": [],
        "roles": [],
        "fields": [],
    }
