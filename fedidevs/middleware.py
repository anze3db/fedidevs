"""Anonymous HTML cache headers so Cloudflare can absorb most GET traffic.

AnonymousCacheMiddleware makes anonymous HTML cacheable at Cloudflare: no
Set-Cookie, no ``Vary: Cookie``, and ``Cache-Control: public, s-maxage=300``.
Authenticated requests, language-cookie requests, and anything that modified
the session stay private so forms and per-user pages keep working.

Junk query params on the accounts index are stripped in ``accounts.views.index``,
not here — that is the only view where unknown keys (``?amp=1``) skip the
starter-packs redirect and run the expensive listing.
"""

from django.conf import settings
from django.utils.cache import patch_vary_headers
from django.utils.deprecation import MiddlewareMixin

_SKIP_PATH_PREFIXES = (
    "/admin/",
    "/__debug__/",
    "/__reload__/",
    "/static/",
    "/media/",
)

ANONYMOUS_CACHE_TTL = 300
_CACHEABLE_CONTENT_TYPES = ("text/html", "text/plain")


def _is_skipped_path(path: str) -> bool:
    if path in {"/csrf", "/csrf/", "/admin"}:
        return True
    return path.startswith(_SKIP_PATH_PREFIXES)


class AnonymousCacheMiddleware(MiddlewareMixin):
    """Public-cache anonymous GET HTML; keep CSRF/session cookies off those responses.

    Forms on cached pages obtain a fresh CSRF cookie+token from ``/csrf/`` via
    JS before POST (see ``static/src/components.js``). Authenticated HTMX POSTs
    still use the ``hx-headers`` token baked into the uncached page.
    """

    def process_response(self, request, response):
        if not _is_publicly_cacheable(request, response):
            content_type = response.get("Content-Type", "")
            if _is_private_request(request) and response.status_code == 200 and content_type.startswith("text/html"):
                response["Cache-Control"] = "private, no-store"
            return response

        response.cookies.clear()
        _drop_vary_cookie(response)
        response["Cache-Control"] = f"public, s-maxage={ANONYMOUS_CACHE_TTL}"
        patch_vary_headers(response, ("Accept-Language",))
        return response


def _is_private_request(request) -> bool:
    if request.COOKIES.get(settings.SESSION_COOKIE_NAME):
        return True
    if request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME):
        return True
    user = getattr(request, "user", None)
    return bool(user is not None and user.is_authenticated)


def _is_publicly_cacheable(request, response) -> bool:
    if request.method not in {"GET", "HEAD"}:
        return False
    if response.status_code != 200:
        return False
    if _is_skipped_path(request.path):
        return False
    content_type = response.get("Content-Type", "")
    if not any(content_type.startswith(prefix) for prefix in _CACHEABLE_CONTENT_TYPES):
        return False
    if _is_private_request(request):
        return False
    session = getattr(request, "session", None)
    return not (session is not None and session.modified)


def _drop_vary_cookie(response) -> None:
    vary = response.get("Vary")
    if not vary:
        return
    kept = [header.strip() for header in vary.split(",") if header.strip().lower() != "cookie"]
    if kept:
        response["Vary"] = ", ".join(kept)
    else:
        del response["Vary"]
