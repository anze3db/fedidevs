import xml.etree.ElementTree as ET

from django.core import management
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from accounts.misskey import emojis_to_mastodon, user_to_mastodon
from accounts.misskey_api import build_miauth_url, is_misskey_family
from accounts.models import Account
from confs.models import Conference, ConferenceAccount


# Create your tests here.
class TestSelectedInstance(TestCase):
    @classmethod
    def setUpTestData(cls):
        Account.objects.create(
            account_id="1",
            instance="mastodon.social",
            username="test",
            acct="test",
            display_name="Test",
            locked=False,
            bot=False,
            discoverable=True,
            noindex=False,
            group=False,
            created_at="2021-01-01T00:00:00.000000+00:00",
            last_status_at=timezone.now(),
            last_sync_at="2021-01-01T00:00:00.000000+00:00",
            followers_count=0,
            following_count=0,
            statuses_count=0,
            note="python",
            url="https://mastodon.social/@test",
            avatar="https://mastodon.social/@test/avatar",
            avatar_static="https://mastodon.social/@test/avatar",
            header="https://mastodon.social/@test/header",
            header_static="https://mastodon.social/@test/header",
            emojis=[],
            roles=[],
            fields=[],
        )
        Account.objects.create(
            account_id="2",
            instance="fosstodon.org",
            username="fosstest",
            acct="fosstest",
            display_name="Test Foss",
            locked=False,
            bot=False,
            discoverable=True,
            noindex=False,
            group=False,
            created_at="2021-01-01T00:00:00.000000+00:00",
            last_status_at=timezone.now(),
            last_sync_at="2021-01-01T00:00:00.000000+00:00",
            followers_count=0,
            following_count=0,
            statuses_count=0,
            note="python",
            url="https://fosstodon.org/@fosstest",
            avatar="https://fosstodon.org/@fosstest/avatar",
            avatar_static="https://fosstodon.org/@fosstest/avatar",
            header="https://fosstodon.org/@fosstest/header",
            header_static="https://fosstodon.org/@fosstest/header",
            emojis=[],
            roles=[],
            fields=[],
        )
        management.call_command("indexer")

    def test_no_selected_instance(self):
        response = self.client.get("/?q=")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["selected_instance"])
        self.assertIsNone(self.client.session.get("selected_instance"))
        self.assertContains(
            response,
            '<a href="https://fosstodon.org/@fosstest"',
        )
        self.assertContains(
            response,
            '<a href="https://mastodon.social/@test"',
        )

    def test_selected_instance(self):
        response = self.client.get("/?selected_instance=mastodon.social")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_instance"], "mastodon.social")
        self.assertEqual(self.client.session["selected_instance"], "mastodon.social")

        self.assertContains(
            response,
            '<a href="https://mastodon.social/@fosstest@fosstodon.org"',
        )
        self.assertContains(
            response,
            '<a href="https://mastodon.social/@test"',
        )

    def test_unselected_instance(self):
        self.client.get("/?selected_instance=mastodon.social")
        response = self.client.get("/?selected_instance=")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["selected_instance"])
        self.assertIsNone(self.client.session.get("selected_instance"))

        self.assertContains(
            response,
            '<a href="https://fosstodon.org/@fosstest"',
        )
        self.assertContains(
            response,
            '<a href="https://mastodon.social/@test"',
        )

    def test_selected_instance_https_truncate(self):
        response = self.client.get("/?selected_instance=https://mastodon.social")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_instance"], "mastodon.social")
        self.assertEqual(self.client.session["selected_instance"], "mastodon.social")

        self.assertContains(
            response,
            '<a href="https://mastodon.social/@fosstest@fosstodon.org"',
        )
        self.assertContains(
            response,
            '<a href="https://mastodon.social/@test"',
        )

    def test_selected_instance_http_truncate(self):
        response = self.client.get("/?selected_instance=https://mastodon.social")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_instance"], "mastodon.social")
        self.assertEqual(self.client.session["selected_instance"], "mastodon.social")

        self.assertContains(
            response,
            '<a href="https://mastodon.social/@fosstest@fosstodon.org"',
        )
        self.assertContains(
            response,
            '<a href="https://mastodon.social/@test"',
        )

    def test_selected_instance_slash_truncate(self):
        response = self.client.get("/?selected_instance=https://mastodon.social/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_instance"], "mastodon.social")
        self.assertEqual(self.client.session["selected_instance"], "mastodon.social")

        self.assertContains(
            response,
            '<a href="https://mastodon.social/@fosstest@fosstodon.org"',
        )
        self.assertContains(
            response,
            '<a href="https://mastodon.social/@test"',
        )

    def test_invalid_selected_instance(self):
        response = self.client.get("/?selected_instance=invalid")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["selected_instance"])
        self.assertIsNone(self.client.session.get("selected_instance"))
        self.assertContains(
            response,
            '<a href="https://fosstodon.org/@fosstest"',
        )
        self.assertContains(
            response,
            '<a href="https://mastodon.social/@test"',
        )

    def test_selected_instance_through_session(self):
        self.client.get("/?selected_instance=mastodon.social")
        response = self.client.get("/?q=")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_instance"], "mastodon.social")
        self.assertEqual(self.client.session["selected_instance"], "mastodon.social")

        self.assertContains(
            response,
            '<a href="https://mastodon.social/@fosstest@fosstodon.org"',
        )
        self.assertContains(
            response,
            '<a href="https://mastodon.social/@test"',
        )


class TestMisskeyAdapter(SimpleTestCase):
    instance = "bohio.icu"

    def _base_user(self, **overrides):
        user = {
            "id": "ak69hse2tjnq0016",
            "username": "Ismael",
            "name": "Ismael",
            "host": None,
            "description": "hello",
            "createdAt": "2026-03-23T04:40:31.226Z",
            "updatedAt": "2026-05-27T03:04:42.724Z",
            "followersCount": 43,
            "followingCount": 271,
            "notesCount": 141,
            "avatarUrl": "https://bohio.icu/files/a.webp",
            "bannerUrl": "https://bohio.icu/files/b.png",
            "isBot": False,
            "isLocked": False,
            "isGroup": False,
            "noindex": False,
            "url": None,
            "uri": None,
            "emojis": {"tux": "https://bohio.icu/files/tux.png"},
            "badgeRoles": [{"name": "Moderator"}],
            "fields": [{"name": "site", "value": "example.com"}],
        }
        user.update(overrides)
        return user

    def test_maps_core_fields(self):
        result = user_to_mastodon(self._base_user(), self.instance)
        self.assertEqual(result["id"], "ak69hse2tjnq0016")
        self.assertEqual(result["username"], "Ismael")
        self.assertEqual(result["acct"], "Ismael")
        self.assertEqual(result["display_name"], "Ismael")
        self.assertEqual(result["followers_count"], 43)
        self.assertEqual(result["following_count"], 271)
        self.assertEqual(result["statuses_count"], 141)
        self.assertEqual(result["note"], "hello")
        self.assertEqual(result["created_at"], "2026-03-23T04:40:31.226Z")
        self.assertEqual(result["last_status_at"], "2026-05-27T03:04:42.724Z")
        self.assertFalse(result["bot"])
        self.assertTrue(result["discoverable"])
        self.assertFalse(result["noindex"])

    def test_falls_back_to_constructed_url_when_local(self):
        result = user_to_mastodon(self._base_user(url=None, uri=None), self.instance)
        # url is the human-facing profile; uri is the canonical actor URI built
        # from the Misskey id (https://host/users/{id}), not the @handle.
        self.assertEqual(result["url"], "https://bohio.icu/@Ismael")
        self.assertEqual(result["uri"], "https://bohio.icu/users/ak69hse2tjnq0016")
        # crawler.main derives instance from url.split("/")[2]; verify it lands.
        self.assertEqual(result["url"].split("/")[2], "bohio.icu")

    def test_remote_user_acct_includes_host(self):
        result = user_to_mastodon(
            self._base_user(host="mastodon.social", url="https://mastodon.social/@Ismael"),
            self.instance,
        )
        self.assertEqual(result["acct"], "Ismael@mastodon.social")
        self.assertEqual(result["url"], "https://mastodon.social/@Ismael")

    def test_emojis_dict_converted_to_list(self):
        result = user_to_mastodon(self._base_user(), self.instance)
        self.assertEqual(
            result["emojis"],
            [
                {
                    "shortcode": "tux",
                    "url": "https://bohio.icu/files/tux.png",
                    "static_url": "https://bohio.icu/files/tux.png",
                    "visible_in_picker": True,
                }
            ],
        )

    def test_emojis_missing_returns_empty_list(self):
        self.assertEqual(emojis_to_mastodon(None), [])
        self.assertEqual(emojis_to_mastodon([]), [])

    def test_noindex_flips_discoverable(self):
        result = user_to_mastodon(self._base_user(noindex=True), self.instance)
        self.assertTrue(result["noindex"])
        self.assertFalse(result["discoverable"])

    def test_missing_required_fields_returns_none(self):
        self.assertIsNone(user_to_mastodon({}, self.instance))
        self.assertIsNone(user_to_mastodon({"id": "x", "username": "y"}, self.instance))

    def test_missing_display_name_falls_back_to_username(self):
        result = user_to_mastodon(self._base_user(name=None), self.instance)
        self.assertEqual(result["display_name"], "Ismael")

    def test_missing_avatar_and_banner_are_empty_strings(self):
        result = user_to_mastodon(self._base_user(avatarUrl=None, bannerUrl=None), self.instance)
        self.assertEqual(result["avatar"], "")
        self.assertEqual(result["avatar_static"], "")
        self.assertEqual(result["header"], "")
        self.assertEqual(result["header_static"], "")


class TestMisskeyApi(SimpleTestCase):
    def test_is_misskey_family(self):
        for name in ("sharkey", "Misskey", "FIREFISH", "iceshrimp", "akkoma", "catodon"):
            self.assertTrue(is_misskey_family(name), name)
        for name in ("mastodon", "pixelfed", "", None):
            self.assertFalse(is_misskey_family(name), name)

    def test_build_miauth_url(self):
        url = build_miauth_url(
            "booping.synth.download",
            "sess-123",
            "https://fedidevs.com/miauth_callback/",
            "fedidevs",
        )
        self.assertTrue(url.startswith("https://booping.synth.download/miauth/sess-123?"))
        self.assertIn("name=fedidevs", url)
        # callback is URL-encoded
        self.assertIn("callback=https%3A%2F%2Ffedidevs.com%2Fmiauth_callback%2F", url)
        # native Misskey permission kinds (not Mastodon scopes), comma-joined
        self.assertIn("permission=read%3Aaccount%2Cread%3Afollowing%2Cwrite%3Afollowing", url)


class TestStaticPages(TestCase):
    def test_developers_on_mastodon(self):
        response = self.client.get("/developers-on-mastodon/")
        self.assertEqual(response.status_code, 200)

    def test_faq(self):
        response = self.client.get("/faq/")
        self.assertEqual(response.status_code, 200)


class TestSitemap(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.conf = Conference.objects.create(
            slug="testconf",
            instances="mastodon.social",
            name="Test Conference",
            start_date=timezone.datetime(2021, 1, 1).date(),
            end_date=timezone.datetime(2021, 1, 1).date(),
            tags="",
        )
        cls.account = Account.objects.create(
            account_id="1",
            instance="mastodon.social",
            username="test",
            acct="test",
            display_name="Test",
            locked=False,
            bot=False,
            discoverable=True,
            noindex=False,
            group=False,
            created_at="2021-01-01T00:00:00.000000+00:00",
            last_status_at=timezone.now(),
            last_sync_at="2021-01-01T00:00:00.000000+00:00",
            followers_count=0,
            following_count=0,
            statuses_count=0,
            note="python",
            url="https://mastodon.social/@test",
            avatar="https://mastodon.social/@test/avatar",
            avatar_static="https://mastodon.social/@test/avatar",
            header="https://mastodon.social/@test/header",
            header_static="https://mastodon.social/@test/header",
            emojis=[],
            roles=[],
            fields=[],
        )
        ConferenceAccount.objects.create(conference=cls.conf, account=cls.account, count=1)

    def test_sitemap(self):
        response = self.client.get("/sitemap.xml")
        urls = [
            "http://testserver/",
            "http://testserver/faq/",
            "http://testserver/developers-on-mastodon/",
            "http://testserver/conferences/",
            "http://testserver/stats/",
            "http://testserver/?f=popular&t=project",
            "http://testserver/?f=best&t=project&posted=recently",
            "http://testserver/python/?f=best&t=human&posted=recently",
            "http://testserver/conferences/typescript/",
            "http://testserver/testconf/",
            "http://testserver/testconf/?date=2021-01-01",
            f"http://testserver/testconf/?date=2021-01-01&account={self.account.id}",
        ]

        self.assertEqual(response.status_code, 200)

        xml = ET.fromstring(response.content)  # noqa: S314
        xml_urls = {url[0].text for url in xml}
        for url in urls:
            with self.subTest(url=url):
                self.assertIn(url, xml_urls)
