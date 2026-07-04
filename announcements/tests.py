import datetime as dt
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from model_bakery import baker

from announcements.models import Announcement


@override_settings(
    FEDIDEVS_BOT_ACCESS_TOKEN="token",
    FEDIDEVS_BOT_API_BASE_URL="https://fosstodon.org",
)
class TestPostAnnouncements(TestCase):
    def setUp(self):
        self.due = baker.make(
            Announcement,
            content="Hello fediverse!",
            visibility="public",
            post_at=dt.datetime(2026, 6, 1, 8, 0, tzinfo=dt.UTC),
            posted_at=None,
        )
        self.not_due = baker.make(
            Announcement,
            content="Not yet",
            post_at=dt.datetime(2026, 6, 3, 18, 0, tzinfo=dt.UTC),
            posted_at=None,
        )

    def _run_at(self, moment: dt.datetime, status_post=None, dry_run=False):
        with (
            mock.patch("announcements.management.commands.postannouncements.timezone.now", return_value=moment),
            mock.patch("announcements.management.commands.postannouncements.Mastodon") as mastodon_cls,
        ):
            client = mastodon_cls.return_value
            client.status_post.return_value = {"url": "https://fosstodon.org/@fedidevs/1"}
            if status_post is not None:
                client.status_post = status_post
            # Dry run is the default; posting tests opt in with --no-dry-run.
            call_command("postannouncements", *([] if dry_run else ["--no-dry-run"]))
        return client.status_post

    def test_dry_run_is_the_default(self):
        status_post = self._run_at(dt.datetime(2026, 6, 1, 9, 0, tzinfo=dt.UTC), dry_run=True)

        status_post.assert_not_called()
        self.due.refresh_from_db()
        self.assertIsNone(self.due.posted_at)

    def test_posts_only_due_announcements(self):
        status_post = self._run_at(dt.datetime(2026, 6, 1, 9, 0, tzinfo=dt.UTC))

        status_post.assert_called_once_with("Hello fediverse!", visibility="public")

        self.due.refresh_from_db()
        self.not_due.refresh_from_db()
        self.assertEqual(self.due.posted_at, dt.datetime(2026, 6, 1, 9, 0, tzinfo=dt.UTC))
        self.assertEqual(self.due.post_url, "https://fosstodon.org/@fedidevs/1")
        self.assertIsNone(self.not_due.posted_at)

    def test_respects_visibility(self):
        self.due.visibility = "unlisted"
        self.due.save()

        status_post = self._run_at(dt.datetime(2026, 6, 1, 9, 0, tzinfo=dt.UTC))

        status_post.assert_called_once_with("Hello fediverse!", visibility="unlisted")

    def test_does_not_repost_already_posted(self):
        self.due.posted_at = timezone.now()
        self.due.save()

        # Both would be due by now, but the first is already posted.
        status_post = self._run_at(dt.datetime(2026, 6, 3, 20, 0, tzinfo=dt.UTC))

        status_post.assert_called_once_with("Not yet", visibility="public")

    def test_records_error_and_leaves_row_unposted(self):
        failing = mock.Mock(side_effect=RuntimeError("boom"))

        self._run_at(dt.datetime(2026, 6, 1, 9, 0, tzinfo=dt.UTC), status_post=failing)

        self.due.refresh_from_db()
        self.assertIsNone(self.due.posted_at)
        self.assertEqual(self.due.post_url, "")
        self.assertIn("boom", self.due.error)

    @override_settings(FEDIDEVS_BOT_ACCESS_TOKEN="")
    def test_skips_when_token_missing(self):
        status_post = self._run_at(dt.datetime(2026, 6, 1, 9, 0, tzinfo=dt.UTC))
        status_post.assert_not_called()
