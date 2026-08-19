import datetime as dt

from django.test import TestCase
from django.urls import reverse


class TestSubscribePages(TestCase):
    def test_subscribe_uses_tailwind_layout(self):
        response = self.client.get(reverse("posts_subscribe"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "pico.min.css")
        self.assertContains(response, "min-h-screen")
        self.assertContains(response, "Subscribe to daily posts")

    def test_subscribe_success_uses_tailwind_layout(self):
        response = self.client.get(reverse("posts_subscribe_success"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "pico.min.css")
        self.assertContains(response, "min-h-screen")
        self.assertContains(response, "You have been subscribed")


class TestDjangoConUSLegacyRedirect(TestCase):
    def test_djangoconus_redirects_to_conference_page(self):
        response = self.client.get(reverse("djangoconus"))
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], reverse("conference", kwargs={"conference_slug": "djangoconus23"}))

    def test_djangoconus_date_redirects(self):
        response = self.client.get(reverse("djangoconus", args=[dt.date(2023, 10, 16)]))
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            reverse("conference", kwargs={"conference_slug": "djangoconus23"}) + "?date=2023-10-16",
        )
