import datetime as dt

from django.test import TestCase

from accounts.models import LANGUAGES, Account, AccountLookup
from stats.models import Daily, store_daily_stats


# Create your tests here.
class TestStats(TestCase):
    def test_all_daily_lang_stats(self):
        for lang in LANGUAGES:
            self.assertTrue(
                hasattr(Daily, lang.code + "_accounts"),
                f"{lang.code} missing from Daily model.",
            )

    def test_store_daily_stats(self):
        store_daily_stats()
        daily = Daily.objects.get(date=dt.date.today())

        self.assertEqual(daily.total_accounts, 0)
        self.assertEqual(daily.python_accounts, 0)

    def test_store_daily_stats_with_accounts(self):
        account = Account.objects.create(
            account_id="2",
            instance="fosstodon.org",
            username="fosstest",
            acct="fosstest",
            display_name="Test Foss",
            locked=False,
            bot=False,
            discoverable=True,
            group=False,
            created_at="2021-01-01T00:00:00.000000+00:00",
            last_status_at="2021-01-01T00:00:00.000000+00:00",
            last_sync_at="2021-01-01T00:00:00.000000+00:00",
            followers_count=0,
            following_count=0,
            statuses_count=0,
            note="",
            url="https://fosstodon.org/@fosstest",
            avatar="https://fosstodon.org/@fosstest/avatar",
            avatar_static="https://fosstodon.org/@fosstest/avatar",
            header="https://fosstodon.org/@fosstest/header",
            header_static="https://fosstodon.org/@fosstest/header",
            emojis=[],
            roles=[],
            fields=[],
        )
        AccountLookup.objects.create(account=account, language="python")

        store_daily_stats()
        daily = Daily.objects.get(date=dt.date.today())

        self.assertEqual(daily.total_accounts, 1)
        self.assertEqual(daily.python_accounts, 1)
