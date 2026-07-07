# from django.test import TestCase

# Create your tests hereo

import datetime as dt
import tempfile
import warnings
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import caches
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from announcements.models import Announcement
from confs.conference_announcements import END_TEMPLATES, START_TEMPLATES
from confs.models import Conference, ConferencePost, ConferenceTag
from confs.og_images import get_conference_og_image_signature, render_conference_og_image
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
            # Only approved conferences are announced; approve by default here.
            "approved_at": self.NOW,
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

        for announcement in (start, end):
            self.assertIn("PyCon Somewhere", announcement.content)
            self.assertIn("https://fedidevs.com/pycon-somewhere/", announcement.content)
            # tags are normalised to hashtags regardless of the stored form.
            self.assertIn("#pycon #python", announcement.content)
            self.assertEqual(announcement.visibility, "public")
            self.assertIsNone(announcement.posted_at)

    def test_uses_one_of_the_message_variations(self):
        conference = self._conference()

        self._sync()

        conference.refresh_from_db()
        start_leads = [t.format(name=conference.name) for t in START_TEMPLATES]
        end_leads = [t.format(name=conference.name) for t in END_TEMPLATES]
        self.assertTrue(any(lead in conference.start_announcement.content for lead in start_leads))
        self.assertTrue(any(lead in conference.end_announcement.content for lead in end_leads))

    def test_variation_is_stable_across_resyncs(self):
        conference = self._conference()
        self._sync()
        conference.refresh_from_db()
        first = conference.start_announcement.content

        self._sync()
        conference.refresh_from_db()

        self.assertEqual(conference.start_announcement.content, first)

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

    def test_skips_pending_conferences(self):
        # A submitted-but-not-yet-approved conference must not be announced.
        self._conference(slug="pending", approved_at=None)

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


class TestCreateConference(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.form_data = {
            "name": "PyCon Test",
            "location": "Berlin, Germany",
            "start_date": "2027-06-01",
            "end_date": "2027-06-03",
            "time_zone": "UTC",
            "website": "https://pycon.test",
            "mastodon": "",
            "description": "A test conference",
            "tags": "#pycon",
        }

    def test_requires_login(self):
        response = self.client.get(reverse("create_conference"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_form_renders_for_authenticated_user(self):
        # The "python" tag is seeded by migration 0031; get_or_create keeps this
        # test working whether or not the row already exists.
        ConferenceTag.objects.get_or_create(slug="python", defaults={"name": "Python", "icon": "languages/python.png"})
        self.client.force_login(self.user)
        response = self.client.get(reverse("create_conference"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add a conference")
        # Icon picker renders the available tags.
        self.assertContains(response, 'alt="Python"')

    def test_submit_creates_pending_conference(self):
        self.client.force_login(self.user)
        with (
            mock.patch("confs.views.send_mail") as send_mail_mock,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(reverse("create_conference"), self.form_data)

        conference = Conference.objects.get(name="PyCon Test")
        self.assertIsNone(conference.approved_at)
        self.assertEqual(conference.created_by, self.user)
        self.assertEqual(conference.posts_after, dt.date(2027, 6, 1))
        self.assertEqual(conference.slug, "pycon-test")
        self.assertRedirects(
            response,
            reverse("conference", kwargs={"conference_slug": conference.slug}),
            fetch_redirect_response=False,
        )
        # The reviewer is emailed to approve the pending submission. (Account
        # gathering is triggered by the post_save signal in confs/apps.py, which
        # is disconnected while tests run.)
        send_mail_mock.assert_called_once()

    def test_rejects_end_date_before_start(self):
        self.client.force_login(self.user)
        data = {**self.form_data, "start_date": "2027-06-03", "end_date": "2027-06-01"}
        response = self.client.post(reverse("create_conference"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Conference.objects.filter(name="PyCon Test").exists())

    def test_slug_collision_is_resolved(self):
        baker.make(Conference, slug="pycon-test")
        self.client.force_login(self.user)
        with (
            mock.patch("confs.views.send_mail"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(reverse("create_conference"), self.form_data)
        self.assertTrue(Conference.objects.filter(slug="pycon-test-2").exists())

    def test_mastodon_handle_is_converted_to_url(self):
        self.client.force_login(self.user)
        data = {**self.form_data, "mastodon": "@djangocon@fosstodon.org"}
        with (
            mock.patch("confs.views.send_mail"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(reverse("create_conference"), data)
        conference = Conference.objects.get(name="PyCon Test")
        self.assertEqual(conference.mastodon, "https://fosstodon.org/@djangocon")

    def test_mastodon_url_is_kept(self):
        self.client.force_login(self.user)
        data = {**self.form_data, "mastodon": "https://fosstodon.org/@djangocon"}
        with (
            mock.patch("confs.views.send_mail"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(reverse("create_conference"), data)
        conference = Conference.objects.get(name="PyCon Test")
        self.assertEqual(conference.mastodon, "https://fosstodon.org/@djangocon")

    def test_advanced_days_are_saved(self):
        self.client.force_login(self.user)
        data = {**self.form_data, "days": "Tutorials, Talks", "day_styles": "blue, red"}
        with (
            mock.patch("confs.views.send_mail"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(reverse("create_conference"), data)
        conference = Conference.objects.get(name="PyCon Test")
        self.assertEqual(conference.days, "Tutorials, Talks")
        self.assertEqual(conference.day_styles, "blue, red")

    def test_rejects_more_than_three_icons(self):
        tags = [ConferenceTag.objects.create(name=f"Tag {i}", slug=f"tag-{i}", icon="star.png") for i in range(4)]
        self.client.force_login(self.user)
        data = {**self.form_data, "conference_tags": [t.id for t in tags]}
        with mock.patch("confs.views.send_mail"), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("create_conference"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Conference.objects.filter(name="PyCon Test").exists())

    def test_selected_icons_are_saved(self):
        tag, _ = ConferenceTag.objects.get_or_create(
            slug="python", defaults={"name": "Python", "icon": "languages/python.png"}
        )
        self.client.force_login(self.user)
        data = {**self.form_data, "conference_tags": [tag.id]}
        with (
            mock.patch("confs.views.send_mail"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(reverse("create_conference"), data)
        conference = Conference.objects.get(name="PyCon Test")
        self.assertEqual(list(conference.conference_tags.all()), [tag])


@override_settings(CACHES=settings.TEST_CACHES)
class TestEditConference(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pw")
        self.other = User.objects.create_user("other", password="pw")
        self.staff = User.objects.create_user("staff", password="pw", is_staff=True)
        self.conference = baker.make(
            Conference,
            name="Original Name",
            created_by=self.owner,
            approved_at=None,
            tags="tag1",
            start_date=dt.date(2099, 1, 1),
            end_date=dt.date(2099, 1, 2),
        )
        self.url = reverse("edit_conference", kwargs={"conference_slug": self.conference.slug})

    def _post_data(self, **overrides):
        data = {
            "name": "Updated Name",
            "location": "Berlin, Germany",
            "start_date": "2099-01-01",
            "end_date": "2099-01-02",
            "time_zone": "UTC",
            "website": "https://example.test",
            "mastodon": "",
            "description": "Updated description",
            "tags": "tag1",
            "days": "",
            "day_styles": "",
        }
        data.update(overrides)
        return data

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_owner_can_view_edit_form(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit conference")

    def test_owner_can_edit(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.url, self._post_data())
        self.conference.refresh_from_db()
        self.assertEqual(self.conference.name, "Updated Name")
        self.assertRedirects(
            response,
            reverse("conference", kwargs={"conference_slug": self.conference.slug}),
            fetch_redirect_response=False,
        )

    def test_staff_can_edit(self):
        self.client.force_login(self.staff)
        self.client.post(self.url, self._post_data(name="Staff Edit"))
        self.conference.refresh_from_db()
        self.assertEqual(self.conference.name, "Staff Edit")

    def test_other_user_forbidden(self):
        self.client.force_login(self.other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_edit_does_not_change_slug(self):
        original_slug = self.conference.slug
        self.client.force_login(self.owner)
        self.client.post(self.url, self._post_data(name="A Totally Different Name"))
        self.conference.refresh_from_db()
        self.assertEqual(self.conference.slug, original_slug)


@override_settings(CACHES=settings.TEST_CACHES)
class TestUnapproveConference(TestCase):
    def setUp(self):
        self.conference = baker.make(Conference, approved_at=timezone.now(), tags="tag1")
        self.staff = User.objects.create_user("staff", password="pw", is_staff=True)
        self.normal = User.objects.create_user("bob", password="pw")
        self.url = reverse("unapprove_conference", kwargs={"conference_slug": self.conference.slug})

    def test_staff_unapproves(self):
        self.client.force_login(self.staff)
        self.client.post(self.url)
        self.conference.refresh_from_db()
        self.assertIsNone(self.conference.approved_at)

    def test_non_staff_forbidden(self):
        self.client.force_login(self.normal)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
        self.conference.refresh_from_db()
        self.assertIsNotNone(self.conference.approved_at)


@override_settings(CACHES=settings.TEST_CACHES)
class TestConferenceApprovalVisibility(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pw")
        self.other = User.objects.create_user("other", password="pw")
        self.approved = baker.make(
            Conference,
            name="Approved Conf",
            approved_at=timezone.now(),
            tags="tag1",
            start_date=dt.date(2099, 1, 1),
            end_date=dt.date(2099, 1, 3),
        )
        self.pending = baker.make(
            Conference,
            name="Pending Conf",
            approved_at=None,
            created_by=self.owner,
            tags="tag1",
            start_date=dt.date(2099, 1, 1),
            end_date=dt.date(2099, 1, 3),
        )

    def test_anonymous_sees_only_approved(self):
        response = self.client.get(reverse("conferences"))
        self.assertContains(response, "Approved Conf")
        self.assertNotContains(response, "Pending Conf")

    def test_owner_sees_own_pending(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("conferences"))
        self.assertContains(response, "Approved Conf")
        self.assertContains(response, "Pending Conf")

    def test_other_user_does_not_see_pending(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("conferences"))
        self.assertNotContains(response, "Pending Conf")

    def test_pending_detail_page_is_viewable(self):
        # The submitter can preview the full page before approval.
        url = reverse("conference", kwargs={"conference_slug": self.pending.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_conference_tag_icon_rendered_in_list(self):
        tag, _ = ConferenceTag.objects.get_or_create(
            slug="python", defaults={"name": "Python", "icon": "languages/python.png"}
        )
        self.approved.conference_tags.add(tag)
        response = self.client.get(reverse("conferences"))
        self.assertContains(response, 'alt="Python"')


@override_settings(CACHES=settings.TEST_CACHES)
class TestApproveConference(TestCase):
    def setUp(self):
        self.conference = baker.make(Conference, approved_at=None, tags="tag1")
        self.staff = User.objects.create_user("staff", password="pw", is_staff=True)
        self.normal = User.objects.create_user("bob", password="pw")
        self.url = reverse("approve_conference", kwargs={"conference_slug": self.conference.slug})

    def test_non_staff_forbidden(self):
        self.client.force_login(self.normal)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
        self.conference.refresh_from_db()
        self.assertIsNone(self.conference.approved_at)

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.conference.refresh_from_db()
        self.assertIsNone(self.conference.approved_at)

    def test_staff_approves(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.url)
        self.conference.refresh_from_db()
        self.assertIsNotNone(self.conference.approved_at)
        self.assertRedirects(
            response,
            reverse("conference", kwargs={"conference_slug": self.conference.slug}),
            fetch_redirect_response=False,
        )

    def test_get_not_allowed(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_staff_sees_approve_button_on_detail(self):
        self.client.force_login(self.staff)
        url = reverse("conference", kwargs={"conference_slug": self.conference.slug})
        response = self.client.get(url)
        self.assertContains(response, "Approve conference")

    def test_anonymous_sees_pending_banner_without_button(self):
        url = reverse("conference", kwargs={"conference_slug": self.conference.slug})
        response = self.client.get(url)
        self.assertContains(response, "pending review")
        self.assertNotContains(response, "Approve conference")


class TestConferenceOgImage(TestCase):
    def _conference(self, **kwargs):
        defaults = {
            "name": "PyCon Somewhere",
            "slug": "pycon-somewhere",
            "location": "Somewhere, Nowhere",
            "start_date": dt.date(2026, 6, 1),
            "end_date": dt.date(2026, 6, 3),
            "tags": "#pycon, python",
        }
        defaults.update(kwargs)
        return baker.make(Conference, **defaults)

    def test_signature_changes_with_visible_content(self):
        conference = self._conference()
        original = get_conference_og_image_signature(conference)

        # A field that does not appear on the card leaves the signature unchanged.
        conference.description = "totally different description"
        self.assertEqual(get_conference_og_image_signature(conference), original)

        # A field that does appear on the card changes it.
        conference.name = "PyCon Elsewhere"
        self.assertNotEqual(get_conference_og_image_signature(conference), original)

    def test_render_writes_file_and_updates_fields(self):
        conference = self._conference(og_image_needs_update=True)
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=Path(media_root)):
                render_conference_og_image(conference)
                conference.refresh_from_db()

                self.assertEqual(conference.og_image.name, "conference_og/pycon-somewhere.png")
                self.assertTrue((Path(media_root) / "conference_og" / "pycon-somewhere.png").is_file())
            self.assertEqual(conference.og_image_signature, get_conference_og_image_signature(conference))
            self.assertFalse(conference.og_image_needs_update)
            self.assertIsNotNone(conference.og_image_updated_at)

    def test_management_command_renders_missing_and_skips_current(self):
        stale = self._conference(slug="stale-conf")
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=Path(media_root)):
                # A conference that is already up to date should be left alone.
                current = self._conference(slug="current-conf")
                render_conference_og_image(current)
                current.refresh_from_db()
                rendered_at = current.og_image_updated_at

                call_command("update_conference_og_images")

                stale.refresh_from_db()
                current.refresh_from_db()
                self.assertTrue(stale.og_image)
                # Untouched — same timestamp as before the command ran.
                self.assertEqual(current.og_image_updated_at, rendered_at)
