import datetime as dt

from django.test import TestCase
from django.utils import timezone

from accounts.models import LANGUAGES, Account, AccountLookup
from posts.models import Post
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

    def test_posts_from_yesterday_are_updated(self):
        today = timezone.now()
        yesterday = today - dt.timedelta(days=1)

        yesterday_stats = Daily.objects.create(
            date=yesterday.date(),
            total_accounts=2,
            python_accounts=1,
            javascript_accounts=0,
            rust_accounts=0,
            ruby_accounts=0,
            golang_accounts=0,
            java_accounts=0,
            kotlin_accounts=0,
            scala_accounts=0,
            swift_accounts=0,
            csharp_accounts=0,
            fsharp_accounts=0,
            dotnet_accounts=0,
            cpp_accounts=0,
            linux_accounts=0,
            haskell_accounts=0,
            ocaml_accounts=0,
            nix_accounts=0,
            opensource_accounts=0,
            php_accounts=0,
        )
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
        Post.objects.create(
            account=account,
            post_id="0",
            url="https://fosstodon.org/@fosstest/1",
            created_at=yesterday.isoformat(),
            content="Hello, world!",
            reblog=False,
            sensitive=False,
            spoiler_text="",
            visibility="public",
            language="python",
            emojis=[],
            replies_count=0,
            reblogs_count=0,
            favourites_count=0,
            mentions=[],
            tags=[],
        )
        Post.objects.create(
            account=account,
            post_id="1",
            url="https://fosstodon.org/@fosstest/1",
            created_at=today.isoformat(),
            content="Hello, world!",
            reblog=False,
            sensitive=False,
            spoiler_text="",
            visibility="public",
            language="python",
            replies_count=0,
            reblogs_count=0,
            favourites_count=0,
            emojis=[],
            mentions=[],
            tags=[],
        )
        store_daily_stats()

        # make sure this doesn't change
        yesterday_stats.refresh_from_db()
        self.assertEqual(yesterday_stats.total_posts, 0)
        self.assertEqual(yesterday_stats.python_posts, 0)
        self.assertEqual(yesterday_stats.total_accounts, 2)

        today_stats = Daily.objects.get(date=today.date())
        self.assertEqual(today_stats.total_posts, 2)
        self.assertEqual(today_stats.python_posts, 2)
        self.assertEqual(today_stats.total_accounts, 1)
