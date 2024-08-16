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

from textwrap import dedent

from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, register_converter
from django.utils import dateparse, timezone

from accounts import views
from accounts.models import FRAMEWORKS, LANGUAGES
from confs import views as confs_views
from confs.models import FRAMEWORKS as CONF_FRAMEWORKS
from confs.models import LANGUAGES as CONF_LANGUAGES
from mastodon_auth import views as mastodon_views
from posts import views as post_views


def robots_txt(_):
    return HttpResponse(
        dedent("""\
        User-agent: *
        Disallow: *page=*
        Disallow: *o=*
        Disallow: *q=*
        Disallow: *p=*
        """),
        content_type="text/plain",
    )


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
CONF_LANG_OR_FRAMEWORK = CONF_LANGUAGES + CONF_FRAMEWORKS

urlpatterns = (
    [
        path("admin/", admin.site.urls),
        path("__debug__/", include("debug_toolbar.urls")),
        path("__reload__/", include("django_browser_reload.urls")),
        path("robots.txt", robots_txt),
        path("", views.index, name="index"),
        path("follow/<int:account_id>", mastodon_views.follow, name="follow"),
        path("redirect/<path:query>", mastodon_views.redirect_to_local, name="redirect"),
        path(
            "switch/account_type/<int:accountlookup_id>/<str:account_type>",
            views.switch_account_type,
            name="switch_account_type",
        ),
        path("mastodon_login/", mastodon_views.login, name="mastodon_login"),
        path("mastodon_logout/", mastodon_views.logout, name="mastodon_logout"),
        path("mastodon_auth/", mastodon_views.auth, name="mastodon_auth"),
        path("faq/", views.faq, name="faq"),
        path(
            "developers-on-mastodon/",
            views.devs_on_mastodon,
            name="developers-on-mastodon",
        ),
        path("conferences/", confs_views.conferences, name="conferences"),
    ]
    + [
        path(
            f"conferences/{lang.code}/",
            confs_views.conferences,
            name=f"conference-{lang.code}",
            kwargs={"lang": lang.code},
        )
        for lang in CONF_LANG_OR_FRAMEWORK
    ]
    + [path(f"{lang.code}/", views.index, name=lang.code, kwargs={"lang": lang.code}) for lang in LANG_OR_FRAMEWORK]
    + [
        path(
            "posts/<date:date>/djangoconus23/",
            post_views.djangoconus,
            name="djangoconus",
        ),
        path("posts/djangoconus23/", post_views.djangoconus, name="djangoconus"),
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
    + [
        path("<str:slug>/", confs_views.conference, name="conference"),
    ]
)
