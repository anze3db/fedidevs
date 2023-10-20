"""fedidevs URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import datetime as dt

from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, register_converter
from django.utils import dateparse, timezone

from accounts import views
from accounts.models import FRAMEWORKS, LANGUAGES
from posts import views as post_views


def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow:", content_type="text/plain")


class DateConverter:
    regex = r"\d{4}-\d{1,2}-\d{1,2}"

    def to_python(self, value: str):
        return timezone.make_aware(dateparse.parse_datetime(value))

    def to_url(self, value):
        return value.strftime("%Y-%m-%d")


register_converter(DateConverter, "date")

LANG_OR_FRAMEWORK = LANGUAGES + FRAMEWORKS

urlpatterns = (
    [
        path("admin/", admin.site.urls),
        path("__debug__/", include("debug_toolbar.urls")),
        path("__reload__/", include("django_browser_reload.urls")),
        path("robots.txt", robots_txt),
        path("faq/", views.faq, name="faq"),
        path(
            "developers-on-mastodon/",
            views.devs_on_mastodon,
            name="developers-on-mastodon",
        ),
        path("", views.index, name="index"),
    ]
    + [
        path(f"{lang.code}/", views.index, name=lang.code, kwargs={"lang": lang.code})
        for lang in LANG_OR_FRAMEWORK
    ]
    + [
        path(
            f"posts/<date:date>/{lang.code}/",
            post_views.index,
            name=f"{lang.code}-posts",
            kwargs={"lang": lang.code},
        )
        for lang in LANG_OR_FRAMEWORK
    ]
    + [
        path(
            "posts/<date:date>/djangoconus23",
            post_views.djangoconus,
            name="djangoconus",
        ),
        path("posts/djangoconus23", post_views.djangoconus, name="djangoconus"),
    ]
    + [
        path(
            f"posts/{lang.code}/",
            post_views.index,
            name=f"{lang.code}-posts",
            kwargs={"lang": lang.code},
        )
        for lang in LANG_OR_FRAMEWORK
    ]
    + [
        path("posts/<date:date>/", post_views.index, name="posts"),
        path("posts/", post_views.index, name="posts"),
    ]
)
