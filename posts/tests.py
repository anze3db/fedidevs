import datetime as dt

from django.test import TestCase
from django.utils import timezone

from accounts.models import Account
from posts.models import Post


# Create your tests here.
class TestPostView(TestCase):
    def test_post_view_redirect(self):
        yesterday = timezone.now().date() - dt.timedelta(days=1)
        result = self.client.get("/posts/")
        self.assertRedirects(result, f"/posts/{yesterday.isoformat()}/")

    def test_empty_view(self):
        result = self.client.get("/posts/2021-01-01/")
        self.assertEqual(200, result.status_code)

        self.assertContains(result, "No results, please check back later!")

    def test_with_results(self):
        account = Account.objects.create(
            account_id="1",
            instance="mastodon.social",
            username="test",
            acct="test",
            display_name="Test",
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
            url="https://mastodon.social/@test",
            avatar="https://mastodon.social/@test/avatar",
            avatar_static="https://mastodon.social/@test/avatar",
            header="https://mastodon.social/@test/header",
            header_static="https://mastodon.social/@test/header",
            emojis=[],
            roles=[],
            fields=[],
        )
        Post.objects.create(
            post_id="1",
            account=account,
            instance="mastodon.social",
            content="This is a test post with some content",
            visibility="public",
            favourites_count=1,
            reblogs_count=0,
            replies_count=0,
            created_at="2021-01-01T00:00:00.000000+00:00",
        )
        result = self.client.get("/posts/2021-01-01/")
        self.assertEqual(200, result.status_code)

        self.assertContains(result, "This is a test post with some content")
