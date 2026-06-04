"""Adapter for Misskey-family forks (Catodon, Firefish, Sharkey, Iceshrimp, ...).

These forks do not implement Mastodon's `/api/v1/directory`, but expose a native
`POST /api/users` endpoint that returns a similar list of local accounts. This
module converts those responses into the Mastodon directory shape the rest of
the crawler already knows how to ingest.
"""

from typing import Any

MISSKEY_USERS_BODY = {
    "limit": 80,
    "sort": "+follower",
    "state": "alive",
    "origin": "local",
}


def emojis_to_mastodon(emojis: Any) -> list[dict[str, Any]]:
    if not isinstance(emojis, dict):
        return []
    return [
        {"shortcode": shortcode, "url": url, "static_url": url, "visible_in_picker": True}
        for shortcode, url in emojis.items()
        if isinstance(url, str)
    ]


def user_to_mastodon(user: dict[str, Any], instance: str) -> dict[str, Any] | None:
    """Map a single Misskey user object to the Mastodon directory shape.

    Returns None when the input is missing fields the crawler treats as required.
    """
    username = user.get("username")
    user_id = user.get("id")
    created_at = user.get("createdAt")
    if not (username and user_id and created_at):
        return None

    host = user.get("host")
    acct = username if host is None else f"{username}@{host}"
    url = user.get("url") or f"https://{instance}/@{username}"
    # `url` is the human-facing profile (https://host/@username), but the
    # ActivityPub actor URI is https://host/users/{id} (the Misskey id, not the
    # @handle). Both are null for local users in /api/users responses, so build
    # the actor URI from the id rather than reusing the profile url.
    uri = user.get("uri") or f"https://{instance}/users/{user_id}"
    avatar = user.get("avatarUrl") or ""
    banner = user.get("bannerUrl") or ""
    noindex = bool(user.get("noindex", False))

    return {
        "id": str(user_id),
        "username": username,
        "acct": acct,
        "display_name": user.get("name") or username,
        "locked": bool(user.get("isLocked", False)),
        "bot": bool(user.get("isBot", False)),
        "discoverable": not noindex,
        "group": bool(user.get("isGroup", False)),
        "noindex": noindex,
        "created_at": created_at,
        # Misskey doesn't expose last-status-at on user listings; updatedAt is
        # the closest proxy and is enough for the skip-inactive-for filter.
        "last_status_at": user.get("updatedAt"),
        "followers_count": user.get("followersCount") or 0,
        "following_count": user.get("followingCount") or 0,
        "statuses_count": user.get("notesCount") or 0,
        "note": user.get("description") or "",
        "url": url,
        "uri": uri,
        "avatar": avatar,
        "avatar_static": avatar,
        "header": banner,
        "header_static": banner,
        "emojis": emojis_to_mastodon(user.get("emojis")),
        "roles": user.get("badgeRoles") or [],
        "fields": user.get("fields") or [],
    }
