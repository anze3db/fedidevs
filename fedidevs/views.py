from textwrap import dedent

from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


def robots_txt(_request):
    return HttpResponse(
        dedent(
            """\
            User-agent: *
            Disallow: /*?
            Disallow: /csrf

            Sitemap: https://fedidevs.com/sitemap.xml
            """
        ),
        content_type="text/plain",
    )


@never_cache
@require_GET
def csrf_token(request):
    """Uncached CSRF cookie+token for anonymous forms on publicly cached pages."""
    response = JsonResponse({"csrfToken": get_token(request)})
    response["Cache-Control"] = "private, no-store"
    response["X-Robots-Tag"] = "noindex"
    return response
