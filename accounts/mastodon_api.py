"""Helpers for parsing Mastodon-API account payloads across server flavours."""


def parse_discoverable(account: dict) -> bool:
    """Pleroma/Akkoma omit the top-level `discoverable` field and expose the
    flag at `source.pleroma.discoverable` instead (Mastodon only includes
    `source` on verify_credentials, so the nested lookup never misfires there).
    """
    discoverable = account.get("discoverable")
    if discoverable is None:
        discoverable = account.get("source", {}).get("pleroma", {}).get("discoverable")
    return discoverable is True
