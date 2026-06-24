from unittest.mock import MagicMock, patch

import httpx
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from mastodon.errors import MastodonAPIError

from accounts.models import Account
from mastodon_auth.forms import MastodonLoginForm
from mastodon_auth.models import AccountAccess, Instance
from mastodon_auth.oauth import AppRegistrationError, register_app


class MastodonLoginFormTests(TestCase):
    def test_cleans_instance_to_ascii_hostname(self):
        cases = {
            "mastodon.social": "mastodon.social",
            "https://Mastodon.Social/@test": "mastodon.social",
            "test@mastodon.social": "mastodon.social",
            "grüne.social": "xn--grne-1ra.social",
            "localhost:8000": "localhost:8000",
        }

        for instance, expected in cases.items():
            with self.subTest(instance=instance):
                form = MastodonLoginForm(data={"instance": instance})

                self.assertTrue(form.is_valid())
                self.assertEqual(form.cleaned_data["instance"], expected)

    def test_rejects_invalid_idna_hostname(self):
        cases = [
            "grne%2ê0social",
            "xn--grne social-uhb",
            "xn--grne%20social-uhb",
        ]

        for instance in cases:
            with self.subTest(instance=instance):
                form = MastodonLoginForm(data={"instance": instance})

                self.assertFalse(form.is_valid())
                self.assertIn("instance", form.errors)


class MastodonLoginViewTests(TestCase):
    @patch("mastodon_auth.views.httpx.get")
    def test_invalid_instance_redirects_before_http_request(self, http_get):
        response = self.client.post("/mastodon_login/", {"instance": "grne%2ê0social"})

        self.assertRedirects(response, "/", fetch_redirect_response=False)
        http_get.assert_not_called()
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(
            messages,
            ["Invalid instance URL. Please enter a valid Mastodon instance domain name."],
        )

    @patch("mastodon_auth.views.Mastodon")
    @patch("mastodon_auth.views.register_app", side_effect=AppRegistrationError(429, "rate limited"))
    @patch("mastodon_auth.views.httpx.get")
    def test_create_app_rate_limited_reuses_existing_credentials(self, http_get, _register, mastodon_cls):
        """If re-registration fails (e.g. the instance returns 429) but we already
        have working credentials, reuse them and proceed with login instead of
        failing."""
        http_get.return_value = MagicMock(status_code=200)
        instance = Instance.objects.create(
            url="det.social",
            client_id="existing-cid",
            client_secret="existing-secret",
            scopes="read",  # != "read follow" -> triggers re-registration attempt
            software="mastodon",
        )
        mastodon_cls.return_value.auth_request_url.return_value = "https://det.social/oauth/authorize?x=1"

        response = self.client.post("/mastodon_login/", {"instance": "det.social"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://det.social/oauth/authorize?x=1")
        # Existing credentials untouched; no new app was registered.
        instance.refresh_from_db()
        self.assertEqual(instance.client_id, "existing-cid")
        self.assertEqual(instance.scopes, "read")
        # auth_request_url used the existing client_id.
        _, kwargs = mastodon_cls.return_value.auth_request_url.call_args
        self.assertEqual(kwargs["client_id"], "existing-cid")
        self.assertFalse([str(m) for m in get_messages(response.wsgi_request)])

    @patch("mastodon_auth.views.detect_software", return_value="mastodon")
    @patch("mastodon_auth.views.register_app", side_effect=AppRegistrationError(429, "rate limited"))
    @patch("mastodon_auth.views.httpx.get")
    def test_create_app_failure_without_existing_credentials_errors(self, http_get, _register, _detect):
        """First-time registration failure with no fallback credentials shows a
        clear 'temporarily unavailable' message instead of a 500 or a misleading
        'not compatible' error."""
        http_get.return_value = MagicMock(status_code=200)

        response = self.client.post("/mastodon_login/", {"instance": "det.social"})

        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertFalse(Instance.objects.filter(url="det.social").exists())
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertEqual(len(messages), 1)
        self.assertIn("temporarily unavailable", messages[0])


class RegisterAppTests(SimpleTestCase):
    _kwargs = {
        "api_base_url": "det.social",
        "client_name": "fedidevs.com",
        "scopes": ("read", "follow"),
        "redirect_uris": "https://fedidevs.com/mastodon_auth/",
        "website": "https://fedidevs.com",
    }

    @patch("mastodon_auth.oauth.httpx.post")
    def test_returns_credentials_on_200(self, post):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"client_id": "cid", "client_secret": "sec"}
        post.return_value = resp

        self.assertEqual(register_app(**self._kwargs), ("cid", "sec"))

    @patch("mastodon_auth.oauth.httpx.post")
    def test_raises_with_status_code_on_429(self, post):
        post.return_value = MagicMock(status_code=429, text="Too Many Requests")

        with self.assertRaises(AppRegistrationError) as ctx:
            register_app(**self._kwargs)
        self.assertEqual(ctx.exception.status_code, 429)

    @patch("mastodon_auth.oauth.httpx.post")
    def test_raises_with_none_status_on_network_error(self, post):
        post.side_effect = httpx.ConnectError("boom")

        with self.assertRaises(AppRegistrationError) as ctx:
            register_app(**self._kwargs)
        self.assertIsNone(ctx.exception.status_code)

    @patch("mastodon_auth.oauth.httpx.post")
    def test_raises_when_credentials_missing_from_body(self, post):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"error": "nope"}
        post.return_value = resp

        with self.assertRaises(AppRegistrationError) as ctx:
            register_app(**self._kwargs)
        self.assertEqual(ctx.exception.status_code, 200)


class MastodonAuthCallbackTests(TestCase):
    @patch("mastodon_auth.views.sync_following")
    @patch("mastodon_auth.views.Mastodon")
    def test_pleroma_granular_scope_mismatch_still_logs_in(self, mastodon_cls, sync_following):
        """Pleroma returns granular granted scopes, which makes mastodon.py's
        log_in() raise MastodonAPIError after the token exchange succeeded. We
        should fall back to the already-set access token rather than 500."""
        instance = Instance.objects.create(
            url="pleroma.example",
            client_id="cid",
            client_secret="secret",
            scopes="read follow",
        )
        state = "test-state"
        cache.set(f"oauth:{state}", instance.id)

        mastodon = MagicMock()
        mastodon.access_token = "the-token"
        mastodon.log_in.side_effect = MastodonAPIError(
            'Granted scopes "read:accounts follow" do not contain all of the requested scopes "read follow".'
        )
        mastodon.me.return_value = {
            "id": "42",
            "username": "alice",
            "acct": "alice",
            "display_name": "Alice",
            "locked": False,
            "bot": False,
            "group": False,
            "discoverable": True,
            "created_at": timezone.now(),
            "followers_count": 0,
            "following_count": 0,
            "statuses_count": 0,
            "note": "",
            "url": "https://pleroma.example/users/alice",
            "avatar": "https://pleroma.example/avatar.png",
            "avatar_static": "https://pleroma.example/avatar.png",
            "header": "https://pleroma.example/header.png",
            "header_static": "https://pleroma.example/header.png",
            "emojis": [],
            "fields": [],
            "roles": [],
        }
        mastodon_cls.return_value = mastodon

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.get("/mastodon_auth/", {"code": "abc", "state": state})

        self.assertEqual(response.status_code, 302)
        access = AccountAccess.objects.get()
        self.assertEqual(access.access_token, "the-token")
        sync_following.delay.assert_called_once()

    @patch("mastodon_auth.views.sync_following")
    @patch("mastodon_auth.views.Mastodon")
    def test_pleroma_null_account_fields_are_coerced(self, mastodon_cls, sync_following):
        """Pleroma's verify_credentials returns null discoverable/group and omits
        counts/avatars. Those map to NOT NULL columns, so they must be coerced to
        safe defaults rather than crashing the account upsert with a 500."""
        instance = Instance.objects.create(
            url="dima.wiso.uni-hamburg.de",
            client_id="cid",
            client_secret="secret",
            scopes="read follow",
        )
        state = "test-state"
        cache.set(f"oauth:{state}", instance.id)

        mastodon = MagicMock()
        mastodon.access_token = "the-token"
        mastodon.log_in.return_value = "the-token"
        # Minimal Pleroma-shaped response: null booleans, missing counts/media.
        mastodon.me.return_value = {
            "id": "1",
            "username": "anze",
            "acct": "anze",
            "display_name": "anze",
            "locked": False,
            "bot": False,
            "group": None,
            "discoverable": None,
            "noindex": None,
            "created_at": timezone.now(),
            "url": "https://dima.wiso.uni-hamburg.de/users/anze",
        }
        mastodon_cls.return_value = mastodon

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.get("/mastodon_auth/", {"code": "abc", "state": state})

        self.assertEqual(response.status_code, 302)
        account = Account.objects.get(account_id="1")
        self.assertFalse(account.discoverable)
        self.assertFalse(account.group)
        self.assertEqual(account.followers_count, 0)
        self.assertEqual(account.following_count, 0)
        self.assertEqual(account.statuses_count, 0)
        self.assertEqual(account.note, "")
        self.assertEqual(account.avatar, "")
        self.assertEqual(account.emojis, [])
        self.assertEqual(account.roles, [])
        self.assertEqual(account.fields, [])
        self.assertEqual(AccountAccess.objects.get().access_token, "the-token")

    @patch("mastodon_auth.views.Mastodon")
    def test_token_exchange_failure_without_token_errors(self, mastodon_cls):
        """A genuine MastodonAPIError with no token must not log the user in."""
        instance = Instance.objects.create(
            url="pleroma.example",
            client_id="cid",
            client_secret="secret",
            scopes="read follow",
        )
        state = "test-state"
        cache.set(f"oauth:{state}", instance.id)

        mastodon = MagicMock()
        mastodon.access_token = None
        mastodon.log_in.side_effect = MastodonAPIError("nope")
        mastodon_cls.return_value = mastodon

        response = self.client.get("/mastodon_auth/", {"code": "abc", "state": state})

        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertFalse(AccountAccess.objects.exists())

    def test_oauth_error_redirect_is_surfaced(self):
        """An OAuth error redirect (?error=...) should show a clear message rather
        than the generic 'invalid request'."""
        response = self.client.get(
            "/mastodon_auth/",
            {"error": "access_denied", "error_description": "denied", "state": "x"},
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertEqual(messages, ["Login was cancelled or rejected by the instance. Please try again."])

    def test_bare_callback_without_params_redirects(self):
        """A callback hit with no OAuth params at all (bookmark/crawler) is handled
        gracefully without erroring."""
        response = self.client.get("/mastodon_auth/")
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertEqual(messages, ["Invalid request, please try again"])
