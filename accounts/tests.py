import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from asgiref.sync import async_to_sync
from django.core import management
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from accounts.activitypub import _media_url, _profile_url, actor_to_account_defaults
from accounts.management.commands.crawler import Command as CrawlerCommand
from accounts.management.commands.instances import process_instances
from accounts.misskey import emojis_to_mastodon, user_to_mastodon
from accounts.misskey_api import build_miauth_url, is_misskey_family
from accounts.models import Account, Instance
from confs.models import Conference, ConferenceAccount


class TestActivityPubActor(SimpleTestCase):
    def test_actor_to_account_defaults_maps_bridged_actor(self):
        actor = {
            "id": "https://fed.brid.gy/tantek.com",
            "type": "Person",
            "preferredUsername": "tantek.com",
            "name": "Tantek Çelik",
            "summary": "hi there",
            "discoverable": True,
            "manuallyApprovesFollowers": False,
            "icon": {"type": "Image", "url": "https://tantek.com/photo.jpg"},
            "url": ["https://fed.brid.gy/r/https://tantek.com/", "https://example.com/x"],
        }
        defaults = actor_to_account_defaults(
            actor, user="tantek.com", handle_domain="tantek.com", instance_model=SimpleNamespace(domain="fed.brid.gy")
        )
        self.assertEqual(defaults["username"], "tantek.com")
        self.assertEqual(defaults["username_at_instance"], "@tantek.com@tantek.com")
        self.assertEqual(defaults["instance"], "fed.brid.gy")  # the actor's home host
        self.assertEqual(defaults["display_name"], "Tantek Çelik")
        self.assertTrue(defaults["discoverable"])
        self.assertFalse(defaults["locked"])
        self.assertFalse(defaults["bot"])
        self.assertEqual(defaults["avatar"], "https://tantek.com/photo.jpg")
        self.assertEqual(defaults["url"], "https://fed.brid.gy/r/https://tantek.com/")
        self.assertEqual(defaults["followers_count"], 0)
        self.assertEqual(defaults["activitypub_id"], "https://fed.brid.gy/tantek.com")
        self.assertIsNotNone(defaults["created_at"])

    def test_actor_to_account_defaults_bot_and_locked(self):
        actor = {
            "id": "https://x.example/users/bot",
            "type": "Service",
            "preferredUsername": "bot",
            "manuallyApprovesFollowers": True,
        }
        defaults = actor_to_account_defaults(
            actor, user="bot", handle_domain="x.example", instance_model=SimpleNamespace(domain="x.example")
        )
        self.assertTrue(defaults["bot"])
        self.assertTrue(defaults["locked"])
        self.assertFalse(defaults["discoverable"])  # absent -> defaults False
        self.assertEqual(defaults["display_name"], "bot")  # falls back to username

    def test_media_and_profile_url_variants(self):
        self.assertEqual(_media_url({"url": "a"}), "a")
        self.assertEqual(_media_url([{"url": "b"}]), "b")
        self.assertEqual(_media_url("c"), "c")
        self.assertEqual(_media_url(None), "")
        self.assertEqual(_profile_url({"id": "i", "url": "https://u"}), "https://u")
        self.assertEqual(_profile_url({"id": "i", "url": [{"href": "https://h"}]}), "https://h")
        self.assertEqual(_profile_url({"id": "https://i"}), "https://i")


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


class TestCrawlerGotosocial(SimpleTestCase):
    """GoToSocial serves /api/v1/directory only when the admin sets
    instance-directory-mode: "open"; the default ("webonly") returns 401. Its
    account entity is Mastodon-shaped but omits `uri` (verified against GTS
    0.22 and its swagger spec)."""

    instance = "gts.example"

    def _gts_directory_account(self):
        # Field set as returned by a real GoToSocial 0.22 open directory
        # (plantsand.coffee), minus GTS extras irrelevant to the crawler.
        return {
            "id": "0174DPK1HYWN64T08G8YK4ZHJC",
            "username": "alice",
            "acct": "alice",
            "display_name": "Alice",
            "locked": False,
            "discoverable": True,
            "indexable": True,
            "noindex": False,
            "group": False,
            "bot": False,
            "created_at": "2022-05-01T12:10:40.000Z",
            "last_status_at": "2026-06-27",
            "followers_count": 1,
            "following_count": 1,
            "statuses_count": 5,
            "note": "hello",
            "url": f"https://{self.instance}/@alice",
            "avatar": f"https://{self.instance}/a.webp",
            "avatar_static": f"https://{self.instance}/a.webp",
            "header": f"https://{self.instance}/h.webp",
            "header_static": f"https://{self.instance}/h.webp",
            "emojis": [],
            "roles": [],
            "fields": [],
        }

    def _fetch(self, cmd, handler, offset=0):
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await cmd.fetch(client, offset, self.instance, 0)

        return async_to_sync(run)()

    def test_auth_gated_directory_caches_unknown_and_skips_misskey_probe(self):
        calls = []

        def handler(request):
            calls.append(request.url.path)
            if request.url.path == "/api/v1/directory":
                return httpx.Response(401, json={"error": "Unauthorized: token not supplied"})
            if request.url.path == "/.well-known/nodeinfo":
                return httpx.Response(200, json={"links": [{"href": f"https://{self.instance}/nodeinfo/2.0"}]})
            if request.url.path == "/nodeinfo/2.0":
                return httpx.Response(200, json={"software": {"name": "gotosocial", "version": "0.22.0"}})
            return httpx.Response(404)

        cmd = CrawlerCommand()
        _, results = self._fetch(cmd, handler)
        self.assertEqual(results, [])
        self.assertEqual(cmd._adapters[self.instance], "unknown")
        # 401 is a config statement, not "endpoint missing": don't probe Misskey.
        self.assertNotIn("/api/users", calls)

        # Later pages short-circuit on the cached adapter without any requests.
        calls.clear()
        _, results = self._fetch(cmd, handler, offset=1)
        self.assertEqual(results, [])
        self.assertEqual(calls, [])

    def test_open_directory_resolves_missing_actor_uri_via_webfinger(self):
        def handler(request):
            if request.url.path == "/api/v1/directory":
                return httpx.Response(200, json=[self._gts_directory_account()])
            if request.url.path == "/.well-known/nodeinfo":
                return httpx.Response(200, json={"links": [{"href": f"https://{self.instance}/nodeinfo/2.0"}]})
            if request.url.path == "/nodeinfo/2.0":
                return httpx.Response(200, json={"software": {"name": "gotosocial", "version": "0.22.0"}})
            if request.url.path == "/.well-known/webfinger":
                return httpx.Response(
                    200,
                    json={
                        "subject": f"acct:alice@{self.instance}",
                        "links": [
                            {
                                "rel": "self",
                                "type": "application/activity+json",
                                "href": f"https://{self.instance}/users/alice",
                            }
                        ],
                    },
                )
            return httpx.Response(404)

        cmd = CrawlerCommand()
        _, results = self._fetch(cmd, handler)
        self.assertEqual(cmd._adapters[self.instance], "mastodon")
        self.assertEqual(len(results), 1)
        # GTS omits `uri`; the crawler resolves the actor id so activitypub_id
        # (used in starter-pack ActivityPub payloads) isn't NULL.
        self.assertEqual(results[0]["uri"], f"https://{self.instance}/users/alice")

    def test_open_directory_on_non_gotosocial_leaves_uri_missing(self):
        webfinger_calls = []

        def handler(request):
            if request.url.path == "/api/v1/directory":
                return httpx.Response(200, json=[self._gts_directory_account()])
            if request.url.path == "/.well-known/nodeinfo":
                return httpx.Response(200, json={"links": [{"href": f"https://{self.instance}/nodeinfo/2.0"}]})
            if request.url.path == "/nodeinfo/2.0":
                return httpx.Response(200, json={"software": {"name": "mastodon", "version": "4.1.0"}})
            if request.url.path == "/.well-known/webfinger":
                webfinger_calls.append(request.url.params["resource"])
                return httpx.Response(404)
            return httpx.Response(404)

        cmd = CrawlerCommand()
        _, results = self._fetch(cmd, handler)
        self.assertEqual(len(results), 1)
        self.assertNotIn("uri", results[0])
        # Old Mastodon also omits `uri`; we don't WebFinger whole directories there.
        self.assertEqual(webfinger_calls, [])


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


class TestInstanceIndexingBridgy(TransactionTestCase):
    """Brid.gy bridge subdomains (e.g. bsky.brid.gy) have no /api/v2/instance and
    301-redirect /api/v1/instance to the canonical fed.brid.gy, which reports a
    null `version`. Exercises the redirect-follow + null-version codepath end to
    end, including the DB upsert against the NOT NULL `version` column."""

    def _run(self, handler):
        # Capture the real class before patching: instances.httpx is the same
        # module object as our httpx, so patching the attribute would otherwise
        # make make_client recurse into itself.
        real_async_client = httpx.AsyncClient

        def make_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_async_client(*args, **kwargs)

        with patch("accounts.management.commands.instances.httpx.AsyncClient", make_client):
            async_to_sync(process_instances)(["bsky.brid.gy"])

    def test_follows_redirect_and_coerces_null_version(self):
        def handler(request):
            host, path = request.url.host, request.url.path
            if host == "bsky.brid.gy" and path == "/api/v2/instance":
                return httpx.Response(404)
            if host == "bsky.brid.gy" and path == "/api/v1/instance":
                return httpx.Response(301, headers={"Location": "https://fed.brid.gy/api/v1/instance"})
            if host == "fed.brid.gy" and path == "/api/v1/instance":
                return httpx.Response(
                    200,
                    json={
                        "uri": "fed.brid.gy",
                        "title": "Bridgy Fed",
                        "description": "Bridging the new social internet",
                        "thumbnail": "https://fed.brid.gy/static/bridgy_logo_with_alpha.png",
                        "registrations": True,
                        "version": None,
                    },
                )
            return httpx.Response(404)

        self._run(handler)

        instance = Instance.objects.get(instance="bsky.brid.gy")
        self.assertEqual(instance.domain, "fed.brid.gy")
        self.assertEqual(instance.title, "Bridgy Fed")
        self.assertEqual(instance.version, "")
        self.assertEqual(instance.registrations, {"enabled": True})
        self.assertEqual(instance.thumbnail, {"url": "https://fed.brid.gy/static/bridgy_logo_with_alpha.png"})
