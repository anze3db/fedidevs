# from django.test import TestCase

# Create your tests hereo

import datetime as dt
import warnings
from unittest import mock

from django.conf import settings
from django.core.cache import caches
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from announcements.models import Announcement
from confs.models import Conference, ConferencePost
from posts.models import Post


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


class TestConfPostFiltersDoNotWarnNaiveDatetime(TestCase):
    """The fwd50/djangoconafrica/dotnetconf pages filter *Post.created_at
    (DateTimeField) by date. Passing a bare date used to coerce to a naive
    datetime and warn under active time zone support; the views now use the
    __date lookup instead."""

    def _assert_no_naive_warning(self, url):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "error",
                message=r"DateTimeField .* received a naive datetime",
                category=RuntimeWarning,
            )
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_fwd50(self):
        self._assert_no_naive_warning(reverse("fwd50"))

    def test_fwd50_with_date(self):
        self._assert_no_naive_warning(reverse("fwd50", args=[dt.date(2023, 11, 6)]))

    def test_djangoconafrica(self):
        self._assert_no_naive_warning(reverse("djangoconafrica"))

    def test_djangoconafrica_with_date(self):
        self._assert_no_naive_warning(reverse("djangoconafrica", args=[dt.date(2023, 11, 7)]))

    def test_dotnetconf(self):
        self._assert_no_naive_warning(reverse("dotnetconf"))

    def test_dotnetconf_with_date(self):
        self._assert_no_naive_warning(reverse("dotnetconf", args=[dt.date(2023, 11, 14)]))


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

        self.assertIn("PyCon Somewhere kicks off today", start.content)
        self.assertIn("That's a wrap on PyCon Somewhere", end.content)
        for announcement in (start, end):
            self.assertIn("https://fedidevs.com/pycon-somewhere/", announcement.content)
            # tags are normalised to hashtags regardless of the stored form.
            self.assertIn("#pycon #python", announcement.content)
            self.assertEqual(announcement.visibility, "public")
            self.assertIsNone(announcement.posted_at)

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
