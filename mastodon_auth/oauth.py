"""Minimal OAuth app registration for Mastodon-compatible instances.

We don't use mastodon.py's ``Mastodon.create_app()`` here because it never checks
the HTTP status code: a 429 (rate-limited ``POST /api/v1/apps``) or any error body
makes it raise ``KeyError`` on ``response['client_id']``, so callers can't tell a
rate limit from a genuinely incompatible instance. We POST with httpx (already used
throughout this app) and surface the status code via ``AppRegistrationError`` so
``login()`` can react precisely — e.g. reuse existing credentials on a transient
failure, or show an accurate message.
"""

from urllib.parse import urlencode

import httpx
from mastodon import Mastodon as BaseMastodon

_TIMEOUT = 10

# nodeinfo software.name values that use Pleroma's OAuth server. (Akkoma is a
# Pleroma fork but is handled via MiAuth elsewhere, so it's not here.)
PLEROMA_SOFTWARE = {"pleroma"}


class Mastodon(BaseMastodon):
    """mastodon.py client whose version check can't recurse forever.

    After the token exchange, ``log_in()`` retries the version check. If the
    instance still rejects ``/api/v1/instance`` (or reports no usable version),
    mastodon.py's ``retrieve_mastodon_version()`` falls back to 1.0.0 and calls
    ``verify_minimum_version()``, which sees the check didn't work and calls
    ``retrieve_mastodon_version()`` again — hitting the instance twice per level
    until ``RecursionError``. The outer call has already set the fallback version,
    so a nested call returns it instead of starting over.
    """

    _retrieving_version = False

    def retrieve_mastodon_version(self, fail_hard=False) -> str:
        if self._retrieving_version:
            return f"{self.mastodon_major}.{self.mastodon_minor}.{self.mastodon_patch}"
        self._retrieving_version = True
        try:
            return super().retrieve_mastodon_version(fail_hard=fail_hard)
        finally:
            self._retrieving_version = False


def is_pleroma(software: str | None) -> bool:
    return (software or "").lower() in PLEROMA_SOFTWARE


def authorize_url(
    *,
    api_base_url: str,
    client_id: str,
    redirect_uri: str,
    scopes: tuple[str, ...],
    state: str,
    force_login: bool = False,
) -> str:
    """Build the OAuth ``/oauth/authorize`` URL to send the user to.

    We build this ourselves instead of using mastodon.py's ``auth_request_url``
    because that method emits junk params (``force_login=False``, ``lang=None`` as
    literal strings) that Pleroma mis-parses, and makes an extra
    ``/.well-known/oauth-authorization-server`` request. Pass ``force_login=True``
    for Pleroma so it always runs the consent flow (which issues a code) instead of
    its broken "already authorized" shortcut that redirects back with no code.
    """
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
    }
    if force_login:
        params["force_login"] = "true"
    return f"https://{api_base_url}/oauth/authorize?{urlencode(params)}"


class AppRegistrationError(Exception):
    """Raised when ``/api/v1/apps`` did not return client credentials.

    ``status_code`` is the HTTP status (e.g. 429 for rate limiting), or ``None``
    when the request never completed (DNS/connection/timeout).
    """

    def __init__(self, status_code: int | None, message: str):
        self.status_code = status_code
        super().__init__(message)


def register_app(
    *,
    api_base_url: str,
    client_name: str,
    scopes: tuple[str, ...],
    redirect_uris: str,
    website: str,
    timeout: float = _TIMEOUT,
) -> tuple[str, str]:
    """Register an OAuth app and return ``(client_id, client_secret)``.

    Raises ``AppRegistrationError`` on any failure, with the HTTP status code when
    available (``None`` for transport errors).
    """
    try:
        response = httpx.post(
            f"https://{api_base_url}/api/v1/apps",
            data={
                "client_name": client_name,
                "scopes": " ".join(scopes),
                "redirect_uris": redirect_uris,
                "website": website,
            },
            headers={"User-Agent": "fedidevs"},
            timeout=timeout,
        )
    except httpx.RequestError as e:
        raise AppRegistrationError(None, f"request failed: {e}") from e

    if response.status_code != 200:
        raise AppRegistrationError(
            response.status_code,
            f"unexpected status {response.status_code}: {response.text[:200]}",
        )

    try:
        body = response.json()
        return body["client_id"], body["client_secret"]
    except (ValueError, KeyError, TypeError) as e:
        raise AppRegistrationError(response.status_code, f"missing credentials in response: {e}") from e
