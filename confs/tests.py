# from django.test import TestCase

# Create your tests hereo

import datetime as dt
import importlib
import json
import tempfile
import warnings
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import caches
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from accounts.models import Account
from announcements.models import Announcement
from confs.conference_announcements import END_TEMPLATES, START_TEMPLATES
from confs.models import Conference, ConferenceAccount, ConferenceLookup, ConferencePost, ConferenceTag
from confs.og_images import get_conference_og_image_signature, render_conference_og_image
from posts.models import Post

LEGACY_MIGRATION_MODULE = "confs.migrations.0033_remove_legacy_conference_tables"
LEGACY_FROM_CONFS = "0032_conference_og_image_conference_og_image_needs_update_and_more"
LEGACY_FROM_POSTS = "0006_post_posts_post_account_7eef7a_idx"


def _legacy_migration():
    return importlib.import_module(LEGACY_MIGRATION_MODULE)


def _legacy_account_fields(**overrides):
    now = timezone.now()
    fields = {
        "account_id": "1",
        "instance": "mastodon.social",
        "username": "user",
        "acct": "user",
        "display_name": "User",
        "locked": False,
        "bot": False,
        "discoverable": True,
        "group": False,
        "created_at": now,
        "last_sync_at": now,
        "followers_count": 0,
        "following_count": 0,
        "statuses_count": 0,
        "note": "",
        "url": "https://mastodon.social/@user",
        "avatar": "https://example.com/a.png",
        "avatar_static": "https://example.com/a.png",
        "header": "https://example.com/h.png",
        "header_static": "https://example.com/h.png",
        "emojis": [],
        "roles": [],
        "fields": [],
    }
    fields.update(overrides)
    return fields


def _legacy_post_fields(account, **overrides):
    now = timezone.now()
    instance = overrides.get("instance") or getattr(account, "instance", "mastodon.social")
    fields = {
        "post_id": "1",
        "instance": instance,
        "created_at": now,
        "visibility": "public",
        "uri": "https://example.com/status/1",
        "url": "https://example.com/@user/1",
        "replies_count": 0,
        "reblogs_count": 0,
        "favourites_count": 0,
        "content": "hello",
        "account": account,
        "media_attachments": [],
        "mentions": [],
        "tags": [],
        "emojis": [],
    }
    fields.update(overrides)
    return fields


def _resolve_account_dict(**overrides):
    fields = _legacy_account_fields(**overrides)
    fields["noindex"] = fields.get("noindex")
    fields["last_status_at"] = fields.get("last_status_at")
    fields["username_at_instance"] = f"@{fields['username']}@{fields['instance']}".lower()
    return fields


class TestPostsAfterDatetime(TestCase):
    def test_none_when_unset(self):
        conference = baker.make(Conference, posts_after=None)
        self.assertIsNone(conference.posts_after_datetime)

    def test_aware_start_of_day_in_conference_timezone(self):
        conference = baker.make(Conference, posts_after=dt.date(2025, 11, 28), time_zone="America/New_York")
        result = conference.posts_after_datetime
        self.assertIsNotNone(result.tzinfo)
        # Midnight 2025-11-28 in New York (EST, UTC-5) is 05:00 UTC.
        self.assertEqual(result, dt.datetime(2025, 11, 28, 5, 0, tzinfo=dt.UTC))


class TestConferencesPage(TestCase):
    def test_conferences_page(self):
        response = self.client.get("/conferences/")
        self.assertEqual(response.status_code, 200)


@override_settings(CACHES=settings.TEST_CACHES)
class TestMigratedLegacyConferences(TestCase):
    """Old hardcoded conference pages now live as Conference rows."""

    def test_legacy_conferences_were_seeded(self):
        slugs = ["fwd50", "djangoconafrica", "dotnetconf", "djangoconus23"]
        conferences = {c.slug: c for c in Conference.objects.filter(slug__in=slugs)}
        self.assertEqual(set(conferences), set(slugs))
        self.assertTrue(conferences["fwd50"].is_approved)
        self.assertEqual(conferences["djangoconus23"].days, "Talks, Talks, Talks, Sprints, Sprints")
        self.assertIn("#djangocon", conferences["djangoconus23"].tags)

    def test_legacy_tables_were_dropped(self):
        tables = set(connection.introspection.table_names())
        self.assertNotIn("confs_fwd50account", tables)
        self.assertNotIn("confs_fwd50post", tables)
        self.assertNotIn("confs_djangoconafricaaccount", tables)
        self.assertNotIn("confs_djangoconafricapost", tables)
        self.assertNotIn("confs_dotnetconfaccount", tables)
        self.assertNotIn("confs_dotnetconfpost", tables)
        self.assertNotIn("posts_djangoconus23post", tables)

    def _assert_no_naive_warning(self, url, expected_status=200):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "error",
                message=r"DateTimeField .* received a naive datetime",
                category=RuntimeWarning,
            )
            response = self.client.get(url)
        self.assertEqual(response.status_code, expected_status)
        return response

    def test_fwd50_page(self):
        response = self._assert_no_naive_warning(reverse("fwd50"))
        self.assertNotContains(response, "pico.min.css")
        self.assertContains(response, "min-h-screen")
        self.assertContains(response, "FWD50")

    def test_fwd50_date_redirects(self):
        response = self._assert_no_naive_warning(reverse("fwd50", args=[dt.date(2023, 11, 6)]), expected_status=301)
        self.assertRedirects(
            response,
            reverse("conference", kwargs={"conference_slug": "fwd50"}) + "?date=2023-11-06",
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_djangoconafrica_page(self):
        response = self._assert_no_naive_warning(reverse("djangoconafrica"))
        self.assertContains(response, "DjangoCon Africa")

    def test_djangoconafrica_date_redirects(self):
        response = self.client.get(reverse("djangoconafrica", args=[dt.date(2023, 11, 7)]))
        self.assertEqual(response.status_code, 301)

    def test_dotnetconf_page(self):
        response = self._assert_no_naive_warning(reverse("dotnetconf"))
        self.assertContains(response, ".NET Conf 2023")

    def test_djangoconus_old_url_redirects(self):
        response = self.client.get(reverse("djangoconus"))
        self.assertRedirects(
            response,
            reverse("conference", kwargs={"conference_slug": "djangoconus23"}),
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_djangoconus_date_redirects(self):
        response = self.client.get(reverse("djangoconus", args=[dt.date(2023, 10, 16)]))
        self.assertRedirects(
            response,
            reverse("conference", kwargs={"conference_slug": "djangoconus23"}) + "?date=2023-10-16",
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_migrated_conference_shows_linked_posts(self):
        conference = Conference.objects.get(slug="fwd50")
        post_content = "Hello from a migrated FWD50 post"
        post = baker.make(Post, content=post_content, visibility="public")
        ConferencePost.objects.create(
            conference=conference,
            post=post,
            created_at="2023-11-06T12:00:00Z",
            visibility="public",
            account=post.account,
        )
        response = self.client.get(reverse("fwd50"))
        self.assertContains(response, post_content)

    def test_account_kwargs_from_json(self):
        migration = _legacy_migration()
        payload = {
            "id": "42",
            "username": "djangocon",
            "acct": "djangocon@fosstodon.org",
            "display_name": "DjangoCon",
            "url": "https://fosstodon.org/@djangocon",
            "locked": False,
            "bot": False,
            "discoverable": True,
            "created_at": "2023-01-01T00:00:00Z",
            "followers_count": 10,
            "following_count": 2,
            "statuses_count": 5,
            "note": "hello",
            "avatar": "https://example.com/a.png",
            "header": "https://example.com/h.png",
            "emojis": [],
            "fields": [],
        }
        kwargs = migration.account_kwargs_from_json(payload)
        self.assertIsNotNone(kwargs)
        self.assertEqual(kwargs["account_id"], "42")
        self.assertEqual(kwargs["instance"], "fosstodon.org")
        self.assertEqual(kwargs["username_at_instance"], "@djangocon@fosstodon.org")
        from_string = migration.account_kwargs_from_json(json.dumps(payload))
        self.assertIsNotNone(from_string)
        self.assertEqual(from_string["account_id"], "42")
        self.assertIsNone(migration.account_kwargs_from_json("not-a-dict"))
        self.assertIsNone(migration.account_kwargs_from_json({"username": "missing-id-and-url"}))


class TestResolveLegacyAccountsAndPosts(TestCase):
    """Matching used by 0033: URL first, then (id, instance), then create."""

    def test_match_existing_account_by_url_when_ids_differ(self):
        existing = baker.make(
            Account,
            account_id="canonical-id",
            instance="mastodon.social",
            username="alice",
            url="https://mastodon.social/@alice",
        )
        resolve = _legacy_migration()._resolve_accounts(
            Account,
            [
                _resolve_account_dict(
                    account_id="crawled-id",
                    instance="other.social",
                    username="alice",
                    url="https://mastodon.social/@alice",
                )
            ],
        )
        matched = resolve(
            {"url": "https://mastodon.social/@alice", "account_id": "crawled-id", "instance": "other.social"}
        )
        self.assertEqual(matched.pk, existing.pk)
        self.assertEqual(Account.objects.filter(url="https://mastodon.social/@alice").count(), 1)

    def test_match_existing_account_by_id_and_instance_when_url_differs(self):
        existing = baker.make(
            Account,
            account_id="pair-id",
            instance="mastodon.social",
            username="bob",
            url="https://old.example/@bob",
        )
        resolve = _legacy_migration()._resolve_accounts(
            Account,
            [
                _resolve_account_dict(
                    account_id="pair-id",
                    instance="mastodon.social",
                    username="bob",
                    url="https://mastodon.social/@bob",
                )
            ],
        )
        matched = resolve(
            {"url": "https://mastodon.social/@bob", "account_id": "pair-id", "instance": "mastodon.social"}
        )
        self.assertEqual(matched.pk, existing.pk)
        self.assertEqual(Account.objects.filter(account_id="pair-id", instance="mastodon.social").count(), 1)

    def test_creates_account_when_neither_url_nor_pair_match(self):
        resolve = _legacy_migration()._resolve_accounts(
            Account,
            [
                _resolve_account_dict(
                    account_id="brand-new",
                    instance="fosstodon.org",
                    username="newuser",
                    url="https://fosstodon.org/@newuser",
                )
            ],
        )
        matched = resolve(
            {"url": "https://fosstodon.org/@newuser", "account_id": "brand-new", "instance": "fosstodon.org"}
        )
        self.assertIsNotNone(matched)
        self.assertEqual(matched.username, "newuser")
        self.assertEqual(Account.objects.filter(url="https://fosstodon.org/@newuser").count(), 1)

    def test_dedupes_same_url_and_same_pair_in_one_batch(self):
        resolve = _legacy_migration()._resolve_accounts(
            Account,
            [
                _resolve_account_dict(
                    account_id="one",
                    instance="mastodon.social",
                    username="shared",
                    url="https://mastodon.social/@shared",
                ),
                _resolve_account_dict(
                    account_id="two",
                    instance="other.social",
                    username="shared",
                    url="https://mastodon.social/@shared",
                ),
                _resolve_account_dict(
                    account_id="one",
                    instance="mastodon.social",
                    username="shared",
                    url="https://other.example/@shared",
                ),
            ],
        )
        first = resolve({"url": "https://mastodon.social/@shared", "account_id": "one", "instance": "mastodon.social"})
        by_url = resolve({"url": "https://mastodon.social/@shared", "account_id": "two", "instance": "other.social"})
        by_pair = resolve({"url": "https://other.example/@shared", "account_id": "one", "instance": "mastodon.social"})
        self.assertEqual(first.pk, by_url.pk)
        self.assertEqual(first.pk, by_pair.pk)
        self.assertEqual(Account.objects.filter(username="shared").count(), 1)

    def test_match_existing_post_by_url_then_by_pair(self):
        account = baker.make(Account, username="carol")
        by_url = baker.make(
            Post,
            account=account,
            post_id="url-post",
            url="https://mastodon.social/@carol/111",
            visibility="public",
        )
        by_pair = baker.make(
            Post,
            account=account,
            post_id="pair-post",
            url="https://old.example/@carol/222",
            visibility="public",
        )
        resolve = _legacy_migration()._resolve_posts(
            Post,
            [
                _legacy_post_fields(
                    account,
                    post_id="other-id",
                    url="https://mastodon.social/@carol/111",
                    content="url-match",
                ),
                _legacy_post_fields(
                    account,
                    post_id="pair-post",
                    url="https://mastodon.social/@carol/222",
                    content="pair-match",
                ),
            ],
        )
        self.assertEqual(
            resolve(_legacy_post_fields(account, post_id="other-id", url="https://mastodon.social/@carol/111")).pk,
            by_url.pk,
        )
        self.assertEqual(
            resolve(_legacy_post_fields(account, post_id="pair-post", url="https://mastodon.social/@carol/222")).pk,
            by_pair.pk,
        )
        self.assertEqual(Post.objects.filter(account=account).count(), 2)


class TestLegacyConferenceDataMigration(TransactionTestCase):
    """Re-run 0033 against mixed legacy + existing Account/Post/Conference rows."""

    serialized_rollback = True

    def _leaf_targets(self):
        executor = MigrationExecutor(connection)
        return list(executor.loader.graph.leaf_nodes())

    def _targets_with(self, overrides):
        replaced = set()
        targets = []
        for app_label, name in self._leaf_targets():
            if app_label in overrides:
                targets.append((app_label, overrides[app_label]))
                replaced.add(app_label)
            else:
                targets.append((app_label, name))
        for app_label, name in overrides.items():
            if app_label not in replaced:
                targets.append((app_label, name))
        return targets

    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)

    def test_copies_overlapping_legacy_rows_without_clobbering_existing_data(self):
        latest = self._leaf_targets()
        from_targets = self._targets_with({"confs": LEGACY_FROM_CONFS, "posts": LEGACY_FROM_POSTS})
        try:
            self._migrate(from_targets)
            self._seed_overlapping_legacy_data()
            self._migrate(latest)
            self._assert_overlapping_legacy_data_migrated()
        finally:
            self._migrate(latest)

    def _seed_overlapping_legacy_data(self):
        state_apps = (
            MigrationExecutor(connection)
            .loader.project_state(self._targets_with({"confs": LEGACY_FROM_CONFS, "posts": LEGACY_FROM_POSTS}))
            .apps
        )
        fwd_account_model = state_apps.get_model("confs", "Fwd50Account")
        fwd_post_model = state_apps.get_model("confs", "Fwd50Post")
        africa_account_model = state_apps.get_model("confs", "DjangoConAfricaAccount")
        africa_post_model = state_apps.get_model("confs", "DjangoConAfricaPost")
        dotnet_account_model = state_apps.get_model("confs", "DotNetConfAccount")
        dotnet_post_model = state_apps.get_model("confs", "DotNetConfPost")
        us_post_model = state_apps.get_model("posts", "DjangoConUS23Post")

        unrelated_account = baker.make(
            Account,
            account_id="unrelated",
            instance="unrelated.example",
            username="nobody",
            url="https://unrelated.example/@nobody",
        )
        baker.make(
            Post,
            account=unrelated_account,
            post_id="unrelated-post",
            url="https://unrelated.example/@nobody/1",
            content="unrelated-post-content",
            visibility="public",
        )

        url_match_account = baker.make(
            Account,
            account_id="canonical-url-match",
            instance="mastodon.social",
            username="urlmatch",
            url="https://mastodon.social/@urlmatch",
        )
        url_match_post = baker.make(
            Post,
            account=url_match_account,
            post_id="canonical-url-post",
            url="https://mastodon.social/@urlmatch/111",
            content="existing-url-match-post",
            visibility="public",
        )

        pair_match_account = baker.make(
            Account,
            account_id="pair-id",
            instance="mastodon.social",
            username="pairmatch",
            url="https://old.example/@pairmatch",
        )
        baker.make(
            Post,
            account=pair_match_account,
            post_id="pair-post",
            url="https://old.example/@pairmatch/222",
            content="existing-pair-match-post",
            visibility="public",
        )

        fwd50 = Conference.objects.create(
            name="Spreadsheet FWD50",
            slug="fwd50",
            location="Ottawa",
            start_date=dt.date(2020, 1, 1),
            end_date=dt.date(2020, 1, 2),
            description="Imported from spreadsheet",
        )
        ConferencePost.objects.create(
            conference=fwd50,
            post=url_match_post,
            created_at=url_match_post.created_at,
            visibility="public",
            account=url_match_account,
        )
        ConferenceAccount.objects.create(conference=fwd50, account=url_match_account, count=99)

        africa = Conference.objects.create(
            name="Spreadsheet DjangoCon Africa",
            slug="djangoconafrica",
            location="Zanzibar",
            start_date=dt.date(2019, 1, 1),
            end_date=dt.date(2019, 1, 2),
            description="Imported from spreadsheet",
        )
        ConferenceLookup.objects.create(conference=africa, language="python")

        self._unrelated_account_pk = unrelated_account.pk
        self._url_match_account_pk = url_match_account.pk
        self._url_match_post_pk = url_match_post.pk
        self._pair_match_account_pk = pair_match_account.pk

        crawled_url_match = fwd_account_model.objects.create(
            **_legacy_account_fields(
                account_id="crawled-url-match",
                instance="other.social",
                username="urlmatch",
                url="https://mastodon.social/@urlmatch",
            )
        )
        fwd_post_model.objects.create(
            **_legacy_post_fields(
                crawled_url_match,
                post_id="crawled-url-post",
                url="https://mastodon.social/@urlmatch/111",
                content="fwd50-url-match-post",
            )
        )

        crawled_pair = fwd_account_model.objects.create(
            **_legacy_account_fields(
                account_id="pair-id",
                instance="mastodon.social",
                username="pairmatch",
                url="https://mastodon.social/@pairmatch",
            )
        )
        fwd_post_model.objects.create(
            **_legacy_post_fields(
                crawled_pair,
                post_id="pair-post",
                url="https://mastodon.social/@pairmatch/222",
                content="fwd50-pair-match-post",
            )
        )

        brand_new = fwd_account_model.objects.create(
            **_legacy_account_fields(
                account_id="brand-new",
                instance="fosstodon.org",
                username="newfwd",
                url="https://fosstodon.org/@newfwd",
            )
        )
        fwd_post_model.objects.create(
            **_legacy_post_fields(
                brand_new,
                post_id="new-1",
                url="https://fosstodon.org/@newfwd/1",
                content="fwd50-new-post-1",
            )
        )
        fwd_post_model.objects.create(
            **_legacy_post_fields(
                brand_new,
                post_id="new-2",
                url="https://fosstodon.org/@newfwd/2",
                content="fwd50-new-post-2",
            )
        )

        shared_fwd = fwd_account_model.objects.create(
            **_legacy_account_fields(
                account_id="shared-fwd",
                instance="hachyderm.io",
                username="shared",
                url="https://hachyderm.io/@shared",
            )
        )
        fwd_post_model.objects.create(
            **_legacy_post_fields(
                shared_fwd,
                post_id="shared-fwd-post",
                url="https://hachyderm.io/@shared/fwd",
                content="fwd50-shared-post",
            )
        )
        shared_africa = africa_account_model.objects.create(
            **_legacy_account_fields(
                account_id="shared-africa",
                instance="mas.to",
                username="shared",
                url="https://hachyderm.io/@shared",
            )
        )
        africa_post_model.objects.create(
            **_legacy_post_fields(
                shared_africa,
                post_id="shared-africa-post",
                url="https://hachyderm.io/@shared/africa",
                content="africa-shared-post",
            )
        )

        africa_only = africa_account_model.objects.create(
            **_legacy_account_fields(
                account_id="africa-only",
                instance="fosstodon.org",
                username="africaonly",
                url="https://fosstodon.org/@africaonly",
            )
        )
        africa_post_model.objects.create(
            **_legacy_post_fields(
                africa_only,
                post_id="africa-only-post",
                url="https://fosstodon.org/@africaonly/1",
                content="africa-only-post",
            )
        )

        dotnet = dotnet_account_model.objects.create(
            **_legacy_account_fields(
                account_id="dotnet-fan",
                instance="mastodon.social",
                username="dotnetfan",
                url="https://mastodon.social/@dotnetfan",
            )
        )
        dotnet_post_model.objects.create(
            **_legacy_post_fields(
                dotnet,
                post_id="dotnet-post",
                url="https://mastodon.social/@dotnetfan/1",
                content="dotnet-post",
            )
        )

        us_dict_account = {
            "id": "us-dict",
            "username": "usdict",
            "url": "https://fosstodon.org/@usdict",
            "display_name": "US Dict",
            "created_at": "2023-01-01T00:00:00Z",
        }
        us_post_model.objects.create(
            **_legacy_post_fields(
                us_dict_account,
                post_id="us-dict-post",
                instance="fosstodon.org",
                url="https://fosstodon.org/@usdict/1",
                content="us-dict-post",
            )
        )
        us_string_account = json.dumps(
            {
                "id": "canonical-url-match",
                "username": "urlmatch",
                "url": "https://mastodon.social/@urlmatch",
            }
        )
        us_post_model.objects.create(
            **_legacy_post_fields(
                us_string_account,
                post_id="us-string-post",
                instance="mastodon.social",
                url="https://mastodon.social/@urlmatch/us",
                content="us-string-json-post",
            )
        )
        us_post_model.objects.create(
            **_legacy_post_fields(
                {"username": "skipped"},
                post_id="us-invalid-post",
                instance="fosstodon.org",
                url="https://fosstodon.org/@skipped/1",
                content="us-invalid-post",
            )
        )

    def _assert_overlapping_legacy_data_migrated(self):
        unrelated = Account.objects.get(pk=self._unrelated_account_pk)
        self.assertEqual(unrelated.url, "https://unrelated.example/@nobody")
        self.assertFalse(ConferencePost.objects.filter(account=unrelated).exists())
        self.assertTrue(Post.objects.filter(content="unrelated-post-content").exists())

        fwd50 = Conference.objects.get(slug="fwd50")
        self.assertEqual(fwd50.name, "Spreadsheet FWD50")
        self.assertEqual(fwd50.start_date, dt.date(2020, 1, 1))

        africa = Conference.objects.get(slug="djangoconafrica")
        self.assertEqual(africa.name, "Spreadsheet DjangoCon Africa")
        self.assertEqual(
            sorted(africa.conferencelookup_set.values_list("language", flat=True)),
            ["django", "python"],
        )

        url_match = Account.objects.get(pk=self._url_match_account_pk)
        self.assertEqual(Account.objects.filter(url="https://mastodon.social/@urlmatch").count(), 1)
        self.assertEqual(
            ConferencePost.objects.get(conference=fwd50, post_id=self._url_match_post_pk).post_id,
            self._url_match_post_pk,
        )
        self.assertEqual(ConferencePost.objects.filter(conference=fwd50, post_id=self._url_match_post_pk).count(), 1)

        pair_match = Account.objects.get(pk=self._pair_match_account_pk)
        self.assertEqual(Account.objects.filter(account_id="pair-id", instance="mastodon.social").count(), 1)
        pair_post = ConferencePost.objects.get(conference=fwd50, post__content="existing-pair-match-post")
        self.assertEqual(pair_post.account_id, pair_match.pk)
        self.assertEqual(Post.objects.filter(post_id="pair-post", account=pair_match).count(), 1)

        brand_new = Account.objects.get(url="https://fosstodon.org/@newfwd")
        self.assertEqual(
            set(
                ConferencePost.objects.filter(conference=fwd50, account=brand_new).values_list(
                    "post__content", flat=True
                )
            ),
            {"fwd50-new-post-1", "fwd50-new-post-2"},
        )

        shared = Account.objects.get(url="https://hachyderm.io/@shared")
        self.assertEqual(Account.objects.filter(url="https://hachyderm.io/@shared").count(), 1)
        self.assertTrue(
            ConferencePost.objects.filter(conference=fwd50, account=shared, post__content="fwd50-shared-post").exists()
        )
        self.assertTrue(
            ConferencePost.objects.filter(
                conference=africa, account=shared, post__content="africa-shared-post"
            ).exists()
        )

        africa_only = Account.objects.get(url="https://fosstodon.org/@africaonly")
        self.assertTrue(
            ConferencePost.objects.filter(
                conference=africa, account=africa_only, post__content="africa-only-post"
            ).exists()
        )

        self.assertTrue(
            ConferencePost.objects.filter(conference__slug="dotnetconf", post__content="dotnet-post").exists()
        )
        self.assertTrue(
            ConferencePost.objects.filter(conference__slug="djangoconus23", post__content="us-dict-post").exists()
        )
        us_linked = ConferencePost.objects.get(conference__slug="djangoconus23", post__content="us-string-json-post")
        self.assertEqual(us_linked.account_id, url_match.pk)
        self.assertFalse(Post.objects.filter(content="us-invalid-post").exists())

        self.assertEqual(
            ConferenceAccount.objects.get(conference=fwd50, account=url_match).count,
            ConferencePost.objects.filter(conference=fwd50, account=url_match).count(),
        )
        self.assertEqual(ConferenceAccount.objects.get(conference=fwd50, account=brand_new).count, 2)
        self.assertEqual(ConferenceAccount.objects.get(conference=fwd50, account=shared).count, 1)
        self.assertEqual(ConferenceAccount.objects.get(conference=africa, account=shared).count, 1)
        self.assertEqual(
            ConferenceAccount.objects.get(conference__slug="djangoconus23", account=url_match).count,
            1,
        )

        tables = set(connection.introspection.table_names())
        self.assertNotIn("confs_fwd50account", tables)
        self.assertNotIn("posts_djangoconus23post", tables)


@override_settings(CACHES=settings.TEST_CACHES)
class TestConferencePage(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Set up data for the whole TestCase
        cls.post_content = "Hello this is my post content"
        cls.conference = baker.make(Conference, start_date="2021-01-01", end_date="2021-01-04", tags="tag1")
        post = baker.make(Post, content=cls.post_content)
        ConferencePost.objects.create(
            conference=cls.conference, post=post, created_at="2021-01-02T00:00:00Z", visibility="public"
        )
        cls.url = reverse("conference", kwargs={"conference_slug": cls.conference.slug})

    def test_posts_after_filter_does_not_warn_naive_datetime(self):
        # posts_after is a DateField; filtering ConferencePost.created_at
        # (DateTimeField) with the bare date used to coerce to a naive datetime
        # and warn under active time zone support.
        self.conference.time_zone = "UTC"
        self.conference.posts_after = dt.date(2021, 1, 1)
        self.conference.save()
        caches["memory"].clear()  # cache_page would otherwise skip the query

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "error",
                message=r"DateTimeField .* received a naive datetime",
                category=RuntimeWarning,
            )
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_conference_with_utc_with_date(self):
        self.conference.time_zone = "UTC"
        self.conference.save()

        response = self.client.get(self.url + "?date=2021-01-02")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Day 2 (1)")
        self.assertContains(response, self.post_content)

    def test_conference_with_utc_with_date_no_posts(self):
        self.conference.time_zone = "UTC"
        self.conference.save()

        response = self.client.get(self.url + "?date=2021-01-01")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Day 2 (1)")
        self.assertNotContains(response, self.post_content)

    def test_conference_with_pacific_with_date(self):
        self.conference.time_zone = "America/Los_Angeles"
        self.conference.save()

        response = self.client.get(self.url + "?date=2021-01-01")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Day 1 (1)")
        self.assertContains(response, self.post_content)

    def test_conference_with_pacific_with_date_no_posts(self):
        self.conference.time_zone = "America/Los_Angeles"
        self.conference.save()

        response = self.client.get(self.url + "?date=2021-01-02")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Day 1 (1)")
        self.assertNotContains(response, self.post_content)

    def test_conference_utc_with_no_filter(self):
        self.conference.time_zone = "UTC"
        self.conference.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Day 2 (1)")
        self.assertContains(response, self.post_content)

    def test_conference_pacific_with_no_filter(self):
        self.conference.time_zone = "America/Los_Angeles"
        self.conference.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Day 1 (1)")
        self.assertContains(response, self.post_content)


class TestSyncAnnouncements(TestCase):
    # Fixed "now" so the June 2026 conferences below count as upcoming.
    NOW = dt.datetime(2026, 5, 1, 12, 0, tzinfo=dt.UTC)

    def _conference(self, **kwargs):
        defaults = {
            "name": "PyCon Somewhere",
            "slug": "pycon-somewhere",
            "start_date": dt.date(2026, 6, 1),
            "end_date": dt.date(2026, 6, 3),
            "time_zone": "UTC",
            "tags": "#pycon, python",
            # Only approved conferences are announced; approve by default here.
            "approved_at": self.NOW,
        }
        defaults.update(kwargs)
        return baker.make(Conference, **defaults)

    def _sync(self):
        with mock.patch("confs.management.commands.syncannouncements.timezone.now", return_value=self.NOW):
            call_command("syncannouncements")

    def test_creates_and_links_start_and_end_announcements(self):
        conference = self._conference()

        self._sync()

        conference.refresh_from_db()
        start = conference.start_announcement
        end = conference.end_announcement
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)

        # post_at is the morning of the start / evening of the end in the conf timezone (UTC here).
        self.assertEqual(start.post_at, dt.datetime(2026, 6, 1, 8, 0, tzinfo=dt.UTC))
        self.assertEqual(end.post_at, dt.datetime(2026, 6, 3, 18, 0, tzinfo=dt.UTC))

        for announcement in (start, end):
            self.assertIn("PyCon Somewhere", announcement.content)
            self.assertIn("https://fedidevs.com/pycon-somewhere/", announcement.content)
            # tags are normalised to hashtags regardless of the stored form.
            self.assertIn("#pycon #python", announcement.content)
            self.assertEqual(announcement.visibility, "public")
            self.assertIsNone(announcement.posted_at)

    def test_uses_one_of_the_message_variations(self):
        conference = self._conference()

        self._sync()

        conference.refresh_from_db()
        start_leads = [t.format(name=conference.name) for t in START_TEMPLATES]
        end_leads = [t.format(name=conference.name) for t in END_TEMPLATES]
        self.assertTrue(any(lead in conference.start_announcement.content for lead in start_leads))
        self.assertTrue(any(lead in conference.end_announcement.content for lead in end_leads))

    def test_variation_is_stable_across_resyncs(self):
        conference = self._conference()
        self._sync()
        conference.refresh_from_db()
        first = conference.start_announcement.content

        self._sync()
        conference.refresh_from_db()

        self.assertEqual(conference.start_announcement.content, first)

    def test_post_at_uses_conference_timezone(self):
        conference = self._conference(time_zone="America/Los_Angeles")

        self._sync()

        conference.refresh_from_db()
        # 08:00 in LA (PDT, UTC-7) on 2026-06-01 is 15:00 UTC.
        self.assertEqual(conference.start_announcement.post_at, dt.datetime(2026, 6, 1, 15, 0, tzinfo=dt.UTC))

    def test_skips_past_and_archived_conferences(self):
        self._conference(slug="past", start_date=dt.date(2020, 1, 1), end_date=dt.date(2020, 1, 3))
        self._conference(slug="archived", archived_date=dt.date(2026, 1, 1))

        self._sync()

        self.assertEqual(Announcement.objects.count(), 0)

    def test_skips_pending_conferences(self):
        # A submitted-but-not-yet-approved conference must not be announced.
        self._conference(slug="pending", approved_at=None)

        self._sync()

        self.assertEqual(Announcement.objects.count(), 0)

    def test_is_idempotent_and_refreshes_unposted_content(self):
        conference = self._conference()
        self._sync()
        conference.refresh_from_db()
        original_start_id = conference.start_announcement_id

        conference.name = "PyCon Renamed"
        conference.save()
        self._sync()

        # No new rows — the same announcements are reused and refreshed.
        self.assertEqual(Announcement.objects.count(), 2)
        conference.refresh_from_db()
        self.assertEqual(conference.start_announcement_id, original_start_id)
        self.assertIn("PyCon Renamed", conference.start_announcement.content)

    def test_leaves_already_posted_announcements_untouched(self):
        conference = self._conference()
        self._sync()
        conference.refresh_from_db()
        start = conference.start_announcement
        start.posted_at = timezone.now()
        start.content = "already posted, do not touch"
        start.save()

        conference.name = "PyCon Renamed"
        conference.save()
        self._sync()

        start.refresh_from_db()
        self.assertEqual(start.content, "already posted, do not touch")


class TestCreateConference(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.form_data = {
            "name": "PyCon Test",
            "location": "Berlin, Germany",
            "start_date": "2027-06-01",
            "end_date": "2027-06-03",
            "time_zone": "UTC",
            "website": "https://pycon.test",
            "mastodon": "",
            "description": "A test conference",
            "tags": "#pycon",
        }

    def test_requires_login(self):
        response = self.client.get(reverse("create_conference"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_form_renders_for_authenticated_user(self):
        # The "python" tag is seeded by migration 0031; get_or_create keeps this
        # test working whether or not the row already exists.
        ConferenceTag.objects.get_or_create(slug="python", defaults={"name": "Python", "icon": "languages/python.png"})
        self.client.force_login(self.user)
        response = self.client.get(reverse("create_conference"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add a conference")
        # Icon picker renders the available tags.
        self.assertContains(response, 'alt="Python"')

    def test_submit_creates_pending_conference(self):
        self.client.force_login(self.user)
        with (
            mock.patch("confs.views.send_mail") as send_mail_mock,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(reverse("create_conference"), self.form_data)

        conference = Conference.objects.get(name="PyCon Test")
        self.assertIsNone(conference.approved_at)
        self.assertEqual(conference.created_by, self.user)
        # Posts from up to 180 days before the start date are shown.
        self.assertEqual(conference.posts_after, dt.date(2027, 6, 1) - dt.timedelta(days=180))
        self.assertEqual(conference.slug, "pycon-test")
        self.assertRedirects(
            response,
            reverse("conference", kwargs={"conference_slug": conference.slug}),
            fetch_redirect_response=False,
        )
        # The reviewer is emailed to approve the pending submission. (Account
        # gathering is triggered by the post_save signal in confs/apps.py, which
        # is disconnected while tests run.)
        send_mail_mock.assert_called_once()

    def test_rejects_end_date_before_start(self):
        self.client.force_login(self.user)
        data = {**self.form_data, "start_date": "2027-06-03", "end_date": "2027-06-01"}
        response = self.client.post(reverse("create_conference"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Conference.objects.filter(name="PyCon Test").exists())

    def test_slug_collision_is_resolved(self):
        baker.make(Conference, slug="pycon-test")
        self.client.force_login(self.user)
        with (
            mock.patch("confs.views.send_mail"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(reverse("create_conference"), self.form_data)
        self.assertTrue(Conference.objects.filter(slug="pycon-test-2").exists())

    def test_mastodon_handle_is_converted_to_url(self):
        self.client.force_login(self.user)
        data = {**self.form_data, "mastodon": "@djangocon@fosstodon.org"}
        with (
            mock.patch("confs.views.send_mail"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(reverse("create_conference"), data)
        conference = Conference.objects.get(name="PyCon Test")
        self.assertEqual(conference.mastodon, "https://fosstodon.org/@djangocon")

    def test_mastodon_url_is_kept(self):
        self.client.force_login(self.user)
        data = {**self.form_data, "mastodon": "https://fosstodon.org/@djangocon"}
        with (
            mock.patch("confs.views.send_mail"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(reverse("create_conference"), data)
        conference = Conference.objects.get(name="PyCon Test")
        self.assertEqual(conference.mastodon, "https://fosstodon.org/@djangocon")

    def test_advanced_days_are_saved(self):
        self.client.force_login(self.user)
        data = {**self.form_data, "days": "Tutorials, Talks", "day_styles": "blue, red"}
        with (
            mock.patch("confs.views.send_mail"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(reverse("create_conference"), data)
        conference = Conference.objects.get(name="PyCon Test")
        self.assertEqual(conference.days, "Tutorials, Talks")
        self.assertEqual(conference.day_styles, "blue, red")

    def test_rejects_more_than_three_icons(self):
        tags = [ConferenceTag.objects.create(name=f"Tag {i}", slug=f"tag-{i}", icon="star.png") for i in range(4)]
        self.client.force_login(self.user)
        data = {**self.form_data, "conference_tags": [t.id for t in tags]}
        with mock.patch("confs.views.send_mail"), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("create_conference"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Conference.objects.filter(name="PyCon Test").exists())

    def test_selected_icons_are_saved(self):
        tag, _ = ConferenceTag.objects.get_or_create(
            slug="python", defaults={"name": "Python", "icon": "languages/python.png"}
        )
        self.client.force_login(self.user)
        data = {**self.form_data, "conference_tags": [tag.id]}
        with (
            mock.patch("confs.views.send_mail"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(reverse("create_conference"), data)
        conference = Conference.objects.get(name="PyCon Test")
        self.assertEqual(list(conference.conference_tags.all()), [tag])


@override_settings(CACHES=settings.TEST_CACHES)
class TestEditConference(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pw")
        self.other = User.objects.create_user("other", password="pw")
        self.staff = User.objects.create_user("staff", password="pw", is_staff=True)
        self.conference = baker.make(
            Conference,
            name="Original Name",
            created_by=self.owner,
            approved_at=None,
            tags="tag1",
            start_date=dt.date(2099, 1, 1),
            end_date=dt.date(2099, 1, 2),
        )
        self.url = reverse("edit_conference", kwargs={"conference_slug": self.conference.slug})

    def _post_data(self, **overrides):
        data = {
            "name": "Updated Name",
            "location": "Berlin, Germany",
            "start_date": "2099-01-01",
            "end_date": "2099-01-02",
            "time_zone": "UTC",
            "website": "https://example.test",
            "mastodon": "",
            "description": "Updated description",
            "tags": "tag1",
            "days": "",
            "day_styles": "",
        }
        data.update(overrides)
        return data

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_owner_can_view_edit_form(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit conference")

    def test_owner_can_edit(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.url, self._post_data())
        self.conference.refresh_from_db()
        self.assertEqual(self.conference.name, "Updated Name")
        self.assertRedirects(
            response,
            reverse("conference", kwargs={"conference_slug": self.conference.slug}),
            fetch_redirect_response=False,
        )

    def test_staff_can_edit(self):
        self.client.force_login(self.staff)
        self.client.post(self.url, self._post_data(name="Staff Edit"))
        self.conference.refresh_from_db()
        self.assertEqual(self.conference.name, "Staff Edit")

    def test_other_user_forbidden(self):
        self.client.force_login(self.other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_edit_does_not_change_slug(self):
        original_slug = self.conference.slug
        self.client.force_login(self.owner)
        self.client.post(self.url, self._post_data(name="A Totally Different Name"))
        self.conference.refresh_from_db()
        self.assertEqual(self.conference.slug, original_slug)


@override_settings(CACHES=settings.TEST_CACHES)
class TestUnapproveConference(TestCase):
    def setUp(self):
        self.conference = baker.make(Conference, approved_at=timezone.now(), tags="tag1")
        self.staff = User.objects.create_user("staff", password="pw", is_staff=True)
        self.normal = User.objects.create_user("bob", password="pw")
        self.url = reverse("unapprove_conference", kwargs={"conference_slug": self.conference.slug})

    def test_staff_unapproves(self):
        self.client.force_login(self.staff)
        self.client.post(self.url)
        self.conference.refresh_from_db()
        self.assertIsNone(self.conference.approved_at)

    def test_non_staff_forbidden(self):
        self.client.force_login(self.normal)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
        self.conference.refresh_from_db()
        self.assertIsNotNone(self.conference.approved_at)


@override_settings(CACHES=settings.TEST_CACHES)
class TestConferenceApprovalVisibility(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pw")
        self.other = User.objects.create_user("other", password="pw")
        self.approved = baker.make(
            Conference,
            name="Approved Conf",
            approved_at=timezone.now(),
            tags="tag1",
            start_date=dt.date(2099, 1, 1),
            end_date=dt.date(2099, 1, 3),
        )
        self.pending = baker.make(
            Conference,
            name="Pending Conf",
            approved_at=None,
            created_by=self.owner,
            tags="tag1",
            start_date=dt.date(2099, 1, 1),
            end_date=dt.date(2099, 1, 3),
        )

    def test_anonymous_sees_only_approved(self):
        response = self.client.get(reverse("conferences"))
        self.assertContains(response, "Approved Conf")
        self.assertNotContains(response, "Pending Conf")

    def test_owner_sees_own_pending(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("conferences"))
        self.assertContains(response, "Approved Conf")
        self.assertContains(response, "Pending Conf")

    def test_other_user_does_not_see_pending(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("conferences"))
        self.assertNotContains(response, "Pending Conf")

    def test_pending_detail_page_is_viewable(self):
        # The submitter can preview the full page before approval.
        url = reverse("conference", kwargs={"conference_slug": self.pending.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_conference_tag_icon_rendered_in_list(self):
        tag, _ = ConferenceTag.objects.get_or_create(
            slug="python", defaults={"name": "Python", "icon": "languages/python.png"}
        )
        self.approved.conference_tags.add(tag)
        response = self.client.get(reverse("conferences"))
        self.assertContains(response, 'alt="Python"')


@override_settings(CACHES=settings.TEST_CACHES)
class TestApproveConference(TestCase):
    def setUp(self):
        self.conference = baker.make(Conference, approved_at=None, tags="tag1")
        self.staff = User.objects.create_user("staff", password="pw", is_staff=True)
        self.normal = User.objects.create_user("bob", password="pw")
        self.url = reverse("approve_conference", kwargs={"conference_slug": self.conference.slug})

    def test_non_staff_forbidden(self):
        self.client.force_login(self.normal)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
        self.conference.refresh_from_db()
        self.assertIsNone(self.conference.approved_at)

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.conference.refresh_from_db()
        self.assertIsNone(self.conference.approved_at)

    def test_staff_approves(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.url)
        self.conference.refresh_from_db()
        self.assertIsNotNone(self.conference.approved_at)
        self.assertRedirects(
            response,
            reverse("conference", kwargs={"conference_slug": self.conference.slug}),
            fetch_redirect_response=False,
        )

    def test_get_not_allowed(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_staff_sees_approve_button_on_detail(self):
        self.client.force_login(self.staff)
        url = reverse("conference", kwargs={"conference_slug": self.conference.slug})
        response = self.client.get(url)
        self.assertContains(response, "Approve conference")

    def test_anonymous_sees_pending_banner_without_button(self):
        url = reverse("conference", kwargs={"conference_slug": self.conference.slug})
        response = self.client.get(url)
        self.assertContains(response, "pending review")
        self.assertNotContains(response, "Approve conference")


class TestConferenceOgImage(TestCase):
    def _conference(self, **kwargs):
        defaults = {
            "name": "PyCon Somewhere",
            "slug": "pycon-somewhere",
            "location": "Somewhere, Nowhere",
            "start_date": dt.date(2026, 6, 1),
            "end_date": dt.date(2026, 6, 3),
            "tags": "#pycon, python",
        }
        defaults.update(kwargs)
        return baker.make(Conference, **defaults)

    def test_signature_changes_with_visible_content(self):
        conference = self._conference()
        original = get_conference_og_image_signature(conference)

        # A field that does not appear on the card leaves the signature unchanged.
        conference.description = "totally different description"
        self.assertEqual(get_conference_og_image_signature(conference), original)

        # A field that does appear on the card changes it.
        conference.name = "PyCon Elsewhere"
        self.assertNotEqual(get_conference_og_image_signature(conference), original)

    def test_render_writes_file_and_updates_fields(self):
        conference = self._conference(og_image_needs_update=True)
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=Path(media_root)):
                render_conference_og_image(conference)
                conference.refresh_from_db()

                self.assertEqual(conference.og_image.name, "conference_og/pycon-somewhere.png")
                self.assertTrue((Path(media_root) / "conference_og" / "pycon-somewhere.png").is_file())
            self.assertEqual(conference.og_image_signature, get_conference_og_image_signature(conference))
            self.assertFalse(conference.og_image_needs_update)
            self.assertIsNotNone(conference.og_image_updated_at)

    def test_management_command_renders_missing_and_skips_current(self):
        stale = self._conference(slug="stale-conf")
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=Path(media_root)):
                # A conference that is already up to date should be left alone.
                current = self._conference(slug="current-conf")
                render_conference_og_image(current)
                current.refresh_from_db()
                rendered_at = current.og_image_updated_at

                call_command("update_conference_og_images")

                stale.refresh_from_db()
                current.refresh_from_db()
                self.assertTrue(stale.og_image)
                # Untouched — same timestamp as before the command ran.
                self.assertEqual(current.og_image_updated_at, rendered_at)
