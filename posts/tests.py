import datetime as dt
import warnings

from django.test import TestCase
from django.urls import reverse


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

    def test_djangoconus(self):
        self._assert_no_naive_warning(reverse("djangoconus"))

    def test_djangoconus_with_date(self):
        self._assert_no_naive_warning(reverse("djangoconus", args=[dt.date(2023, 10, 16)]))
