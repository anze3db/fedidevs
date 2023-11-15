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
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, register_converter
from django.utils import dateparse, timezone

from accounts import views
from accounts.models import FRAMEWORKS, LANGUAGES
from confs import views as confs_views
from posts import views as post_views


def robots_txt(_):
    return HttpResponse("User-agent: *\nDisallow:", content_type="text/plain")


class DateConverter:
    regex = r"\d{4}-\d{1,2}-\d{1,2}"

    def to_python(self, value: str):
        if dt := dateparse.parse_datetime(value):
            return timezone.make_aware(dt)
        return None

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
        path("posts/subscribe", post_views.subscribe, name="posts_subscribe"),
        path(
            "posts/subscribe/success",
            post_views.subscribe_success,
            name="posts_subscribe_success",
        ),
    ]
    + [path(f"{lang.code}/", views.index, name=lang.code, kwargs={"lang": lang.code}) for lang in LANG_OR_FRAMEWORK]
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
    + [
        path("fwd50/", confs_views.fwd50, name="fwd50"),
        path(
            "fwd50/<date:date>/",
            confs_views.fwd50,
            name="fwd50",
        ),
        path("djangoconafrica/", confs_views.djangoconafrica, name="djangoconafrica"),
        path(
            "djangoconafrica/<date:date>/",
            confs_views.djangoconafrica,
            name="djangoconafrica",
        ),
        path("dotnetconf/", confs_views.dotnetconf, name="dotnetconf"),
        path(
            "dotnetconf/<date:date>/",
            confs_views.dotnetconf,
            name="dotnetconf",
        ),
    ]
)
