"""Remote-follow support for starter packs (issue #182).

Servers without a Mastodon-compatible client API or MiAuth (e.g. the WordPress
ActivityPub plugin) can't go through our OAuth login, but almost every fediverse
server advertises an OStatus subscribe endpoint in its WebFinger response:

    {"rel": "http://ostatus.org/schema/1.0/subscribe",
     "template": "https://example.social/authorize_interaction?uri={uri}"}

We ask the visitor for their handle, look up that template on their home server,
and redirect them to it with the starter pack's ActivityPub Collection URL as
the ``uri`` — their own server then handles the import/confirmation.
See https://www.w3.org/community/ostatus/wiki/Howto.html
"""

import logging
import re
from urllib.parse import quote

import httpx
import idna

logger = logging.getLogger(__name__)

SUBSCRIBE_REL = "http://ostatus.org/schema/1.0/subscribe"
_TIMEOUT = 10

# user@domain with an optional leading @; the same shape as views.username_regex
# but anchored on a required domain dot so bare usernames are rejected early.
handle_regex = re.compile(r"^@?([^@\s]+)@([^@\s]+\.[^@\s]+)$")


def parse_handle(raw: str) -> tuple[str, str] | None:
    """Split ``[@]user@domain`` into (user, ascii_domain), or None if invalid.

    The domain is IDNA-encoded so unicode instance names work in the WebFinger
    URL, mirroring what MastodonLoginForm does for instance domains.
    """
    match = handle_regex.match(raw.strip())
    if not match:
        return None
    user, domain = match.groups()
    try:
        ascii_domain = idna.encode(domain.rstrip("."), uts46=True).decode("ascii")
    except idna.IDNAError:
        return None
    return user, ascii_domain


def get_subscribe_url(user: str, domain: str, target_uri: str) -> str | None:
    """WebFinger ``acct:user@domain`` -> its subscribe template filled with target_uri.

    Returns None when the account doesn't resolve or its server doesn't
    advertise a usable https subscribe template.
    """
    try:
        res = httpx.get(
            f"https://{domain}/.well-known/webfinger",
            params={"resource": f"acct:{user}@{domain}"},
            headers={"Accept": "application/jrd+json", "User-Agent": "fedidevs"},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        logger.info("Remote follow WebFinger failed for %s@%s", user, domain)
        return None
    if res.status_code != 200:
        logger.info("Remote follow WebFinger returned %s for %s@%s", res.status_code, user, domain)
        return None
    try:
        links = res.json().get("links", [])
    except ValueError:
        return None
    if not isinstance(links, list):
        return None
    for link in links:
        if not isinstance(link, dict) or link.get("rel") != SUBSCRIBE_REL:
            continue
        template = link.get("template") or ""
        # Require https and the {uri} placeholder so we never redirect the
        # visitor to a javascript:/data: URL a malicious server could serve.
        if template.startswith("https://") and "{uri}" in template:
            return template.replace("{uri}", quote(target_uri, safe=""))
        logger.info("Remote follow unusable subscribe template for %s@%s: %r", user, domain, template)
    return None
