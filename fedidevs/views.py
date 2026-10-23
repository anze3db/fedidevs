from functools import cache
from textwrap import dedent

from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from potatoq import current_app
from potatoq.dashboard import Dashboard


def robots_txt(_request):
    return HttpResponse(
        dedent(
            """\
            User-agent: Googlebot
            Allow: /

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


@cache
def _potatoq_dashboard(app):
    return Dashboard(app)


# potatoq.contrib.django.dashboard only lets in is_staff users, so this mounts the
# dashboard itself to also admit superusers. Django's CSRF token isn't needed: the
# dashboard's actions require an X-Potatoq-Dashboard header that a cross-site form
# can't send.
@csrf_exempt
def potatoq_dashboard(request, path):
    user = request.user
    if not user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if not (user.is_active and (user.is_staff or user.is_superuser)):
        return HttpResponseForbidden("The potatoq dashboard is for staff users")
    headers = {name.lower(): value for name, value in request.headers.items()}
    result = _potatoq_dashboard(current_app()).handle(
        request.method, "/" + path, request.META.get("QUERY_STRING", ""), headers
    )
    response = HttpResponse(result.body, status=result.status)
    for name, value in result.headers:
        response[name] = value
    return response
