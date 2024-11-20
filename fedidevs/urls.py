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
from textwrap import dedent

from django.contrib import admin
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import include, path, register_converter, reverse
from django.utils import dateparse, timezone

from accounts import views
from accounts.models import FRAMEWORKS, LANGUAGES
from confs import views as confs_views
from confs.models import FRAMEWORKS as CONF_FRAMEWORKS
from confs.models import LANGUAGES as CONF_LANGUAGES
from confs.models import Conference, ConferenceAccount
from mastodon_auth import views as mastodon_views
from posts import views as post_views
from starter_packs import views as starter_packs_views
from stats import views as stats_views


def robots_txt(_):
    return HttpResponse(
        dedent("""\
        User-agent: *
        Disallow:
        """),
        content_type="text/plain",
    )


class StaticViewSitemap(Sitemap):
    """
    Sitemap for serving any static content you want.
    """

    def items(self):
        # add any urls (by name) for static content you want to appear in your sitemap to this list
        return [
            "faq",
            "developers-on-mastodon",
            "conferences",
            "stats",
        ]

    def location(self, item):
        return reverse(item)


class AccountSitemap(Sitemap):
    def items(self):
        lang_or_frameworks = [lang.code for lang in LANG_OR_FRAMEWORK] + [None]
        best_or_popular = ["best", "popular", None]
        human_or_project = ["human", "project", None]
        recently_posted = ["recently", None]
        return [
            (
                lang,
                bc,
                hp,
                rp,
            )
            for lang in lang_or_frameworks
            for bc in best_or_popular
            for hp in human_or_project
            for rp in recently_posted
        ]

    def location(self, item):
        lang, best_or_popular, human_or_project, recently_posted = item
        if not best_or_popular and not human_or_project and not recently_posted:
            return reverse("index", kwargs={"lang": lang} if lang else {})
        qs = []
        if best_or_popular:
            qs.append(f"f={best_or_popular}")
        if human_or_project:
            qs.append(f"t={human_or_project}")
        if recently_posted:
            qs.append(f"posted={recently_posted}")
        return reverse("index", kwargs={"lang": lang} if lang else {}) + "?" + "&".join(qs)


class ConferencesSitemap(Sitemap):
    def items(self):
        return [lang.code for lang in CONF_LANG_OR_FRAMEWORK] + [None]

    def location(self, item):
        return reverse("conferences", kwargs={"lang": item})


class ConferenceSitemap(Sitemap):
    def items(self):
        return (
            [
                (conf.slug, account, conf.start_date + dt.timedelta(days=i))
                for conf in Conference.objects.all()
                for account in ConferenceAccount.objects.filter(conference=conf)
                .values_list("account_id", flat=True)
                .filter(count__gt=0)
                .order_by("-count")[:10]
                for i in range((conf.end_date - conf.start_date).days + 1)
                if conf.start_date + dt.timedelta(i) < timezone.now().date()
            ]
            + [
                (conf.slug, None, conf.start_date + dt.timedelta(days=i))
                for conf in Conference.objects.all()
                for i in range((conf.end_date - conf.start_date).days + 1)
                if conf.start_date + dt.timedelta(i) < timezone.now().date()
            ]
            + [(conf.slug, None, None) for conf in Conference.objects.all()]
        )

    def location(self, item):
        conf, account, date = item
        if not date:
            return reverse("conference", kwargs={"conference_slug": conf})

        qs = []
        if date:
            qs.append(f"date={date}")
        if account:
            qs.append(f"account={account}")
        return reverse("conference", kwargs={"conference_slug": conf}) + "?" + "&".join(qs)


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


class LangSlugConverter:
    regex = "|".join([lang.code for lang in LANG_OR_FRAMEWORK]) + "|"

    def to_python(self, value: str):
        return value

    def to_url(self, value):
        if not value:
            return ""
        return value


class ConfLangSlugConverter:
    regex = "|".join([lang.code for lang in CONF_LANG_OR_FRAMEWORK]) + "|"

    def to_python(self, value: str):
        return value

    def to_url(self, value):
        if not value:
            return ""
        return value


register_converter(LangSlugConverter, "langslug")
register_converter(ConfLangSlugConverter, "conflangslug")


urlpatterns = [
    path(
        "sitemap.xml",
        sitemap,
        {
            "sitemaps": {
                "static": StaticViewSitemap(),
                "accounts": AccountSitemap(),
                "conferences": ConferencesSitemap(),
                "conference": ConferenceSitemap(),
            }
        },
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path("admin/", admin.site.urls),
    path("__debug__/", include("debug_toolbar.urls")),
    path("__reload__/", include("django_browser_reload.urls")),
    path("robots.txt", robots_txt),
    path("", views.index, name="index"),
    path("<langslug:lang>/", views.index, name="index"),
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
    path("conferences/<conflangslug:lang>/", confs_views.conferences, name="conferences"),
    path("posts/subscribe", post_views.subscribe, name="posts_subscribe"),
    path(
        "posts/subscribe/success/",
        post_views.subscribe_success,
        name="posts_subscribe_success",
    ),
    path("stats/", stats_views.stats, name="stats"),
    path(
        "posts/<date:date>/djangoconus23/",
        post_views.djangoconus,
        name="djangoconus",
    ),
    path("posts/djangoconus23/", post_views.djangoconus, name="djangoconus"),
    path(
        "starter-packs/add/<str:starter_pack_slug>/",
        starter_packs_views.add_accounts_to_starter_pack,
        name="add_starter_packs",
    ),
    path("starter-packs/create/", starter_packs_views.create_starter_pack, name="create_starter_pack"),
    path(
        "starter-packs/edit/<str:starter_pack_slug>/", starter_packs_views.edit_starter_pack, name="edit_starter_pack"
    ),
    path("starter-packs/", starter_packs_views.starter_packs, name="starter_packs"),
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
    path("<slug:conference_slug>/", confs_views.conference, name="conference"),
]
