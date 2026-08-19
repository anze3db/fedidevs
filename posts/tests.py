import datetime as dt
import warnings

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


class TestDjangoConUSFiltersDoNotWarnNaiveDatetime(TestCase):
    """The djangoconus page filters DjangoConUS23Post.created_at (DateTimeField)
    by date. Passing a bare date used to coerce to a naive datetime and warn
    under active time zone support; the view now uses the __date lookup."""

    def _assert_no_naive_warning(self, url):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "error",
                message=r"DateTimeField .* received a naive datetime",
                category=RuntimeWarning,
            )
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response

    def test_djangoconus(self):
        response = self._assert_no_naive_warning(reverse("djangoconus"))
        self.assertNotContains(response, "pico.min.css")
        self.assertContains(response, "min-h-screen")

    def test_djangoconus_with_date(self):
        self._assert_no_naive_warning(reverse("djangoconus", args=[dt.date(2023, 10, 16)]))
