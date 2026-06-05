"""Native Misskey-family auth + follow client.

Sharkey/Misskey/Firefish/… *do* ship a Mastodon-compatible API, but its OAuth
consent page errors out and the compat layer is unreliable, so for the
Misskey family we talk to the native API instead:

- **Login** uses MiAuth (the native "fancier" consent screen), not OAuth — there
  is no app registration, just a per-login session UUID.
- **Follow / sync** use the native endpoints (`/api/following/create`,
  `/api/users/following`) and resolve remote accounts to a local user id via
  `/api/ap/show` (the native equivalent of Mastodon's `account_search?resolve`).

Everything here is synchronous httpx to match the auth views and Celery tasks.
The functions are deliberately small and side-effect free where possible so the
URL/scope logic can be unit-tested without a live instance.
"""

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

# nodeinfo `software.name` values we treat as the Misskey family.
MISSKEY_SOFTWARE = {
    "misskey",
    "sharkey",
    "firefish",
    "iceshrimp",
    "catodon",
    "akkoma",
    "cherrypick",
    "foundkey",
}

# Misskey-native permission kinds (NOT Mastodon scopes). fedidevs only needs to
# read the logged-in account, read its following list, and follow accounts.
MIAUTH_PERMISSIONS = ("read:account", "read:following", "write:following")

_TIMEOUT = 15


class MisskeyError(Exception):
    """Raised when a native Misskey API call fails."""


def is_misskey_family(software: str | None) -> bool:
    return (software or "").lower() in MISSKEY_SOFTWARE


def detect_software(instance: str) -> str | None:
    """Return the nodeinfo `software.name` for an instance, or None on failure.

    Used at login to decide between the Mastodon (OAuth) and Misskey (MiAuth)
    flows. Failing closed (None) keeps the existing Mastodon path as the default.
    """
    try:
        disco = httpx.get(f"https://{instance}/.well-known/nodeinfo", timeout=_TIMEOUT, follow_redirects=True)
        href = disco.json()["links"][-1]["href"]
        node = httpx.get(href, timeout=_TIMEOUT, follow_redirects=True)
        return (node.json().get("software") or {}).get("name")
    except httpx.HTTPError, KeyError, IndexError, ValueError:
        logger.info("Could not detect software for %s", instance)
        return None


def build_miauth_url(
    instance: str,
    session: str,
    callback: str,
    name: str,
    permissions: tuple[str, ...] = MIAUTH_PERMISSIONS,
) -> str:
    """Build the MiAuth consent URL the user is redirected to.

    Misskey appends `?session=<session>` to `callback` after the user approves.
    """
    query = urlencode({"name": name, "callback": callback, "permission": ",".join(permissions)})
    return f"https://{instance}/miauth/{session}?{query}"


def _api(instance: str, endpoint: str, token: str | None = None, **body: Any) -> Any:
    """POST to a native Misskey API endpoint. Auth via the `i` field in the body."""
    payload: dict[str, Any] = dict(body)
    if token:
        payload["i"] = token
    response = httpx.post(f"https://{instance}/api/{endpoint}", json=payload, timeout=_TIMEOUT)
    response.raise_for_status()
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def miauth_check(instance: str, session: str) -> dict[str, Any] | None:
    """Exchange an approved MiAuth session for `{token, user}`. None if not ok."""
    try:
        data = httpx.post(f"https://{instance}/api/miauth/{session}/check", timeout=_TIMEOUT).json()
    except httpx.HTTPError, ValueError:
        logger.info("MiAuth check failed for %s", instance)
        return None
    if not isinstance(data, dict) or not data.get("ok") or not data.get("token"):
        return None
    return data


def get_following_urls(instance: str, token: str, user_id: str) -> list[str]:
    """Return the profile URLs of everyone the user follows (paginated)."""
    urls: list[str] = []
    until: str | None = None
    while True:
        body: dict[str, Any] = {"userId": user_id, "limit": 100}
        if until:
            body["untilId"] = until
        try:
            page = _api(instance, "users/following", token, **body)
        except httpx.HTTPError:
            logger.info("Error fetching Misskey following for %s", instance)
            break
        if not page:
            break
        for relation in page:
            followee = relation.get("followee") or {}
            url = followee.get("url") or followee.get("uri")
            if not url and followee.get("username"):
                host = followee.get("host") or instance
                url = f"https://{host}/@{followee['username']}"
            if url:
                urls.append(url)
        if len(page) < 100:
            break
        until = page[-1]["id"]
    return urls


def resolve_actor_id(instance: str, token: str, uri: str) -> str | None:
    """Resolve a (possibly remote) ActivityPub actor URI to a local user id.

    Native equivalent of Mastodon's `account_search(resolve=True)`.
    """
    try:
        data = _api(instance, "ap/show", token, uri=uri)
    except httpx.HTTPError:
        logger.info("Could not resolve %s on %s", uri, instance)
        return None
    if isinstance(data, dict) and data.get("type") == "User":
        return (data.get("object") or {}).get("id")
    return None


def follow_user(instance: str, token: str, user_id: str) -> None:
    """Follow a local user id. Treats an already-following state as success."""
    try:
        _api(instance, "following/create", token, userId=user_id)
    except httpx.HTTPStatusError as e:
        # Misskey returns 400 ALREADY_FOLLOWING when the follow already exists;
        # that is success for our purposes, not an error.
        body = e.response.text or ""
        if "ALREADY_FOLLOWING" in body or "ALREADY_REQUESTED" in body:
            return
        message = f"follow failed: {body[:200]}"
        raise MisskeyError(message) from e
