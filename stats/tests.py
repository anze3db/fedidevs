from django.test import TestCase

from accounts.models import LANGUAGES
from stats.models import Daily


# Create your tests here.
class TestStats(TestCase):
    def test_all_daily_lang_stats(self):
        for lang in LANGUAGES:
            self.assertTrue(
                hasattr(Daily, lang.code + "_accounts"),
                f"{lang.code} missing from Daily model.",
            )
