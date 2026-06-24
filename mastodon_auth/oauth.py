"""Minimal OAuth app registration for Mastodon-compatible instances.

We don't use mastodon.py's ``Mastodon.create_app()`` here because it never checks
the HTTP status code: a 429 (rate-limited ``POST /api/v1/apps``) or any error body
makes it raise ``KeyError`` on ``response['client_id']``, so callers can't tell a
rate limit from a genuinely incompatible instance. We POST with httpx (already used
throughout this app) and surface the status code via ``AppRegistrationError`` so
``login()`` can react precisely — e.g. reuse existing credentials on a transient
failure, or show an accurate message.
"""

import httpx

_TIMEOUT = 10


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
