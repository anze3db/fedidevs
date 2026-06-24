# from django.test import TestCase

# Create your tests hereo

import datetime as dt
import warnings

from django.conf import settings
from django.core.cache import caches
from django.test import TestCase, override_settings
from django.urls import reverse
from model_bakery import baker

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
