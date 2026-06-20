from unittest.mock import MagicMock, patch

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from mastodon.errors import MastodonAPIError

from mastodon_auth.forms import MastodonLoginForm
from mastodon_auth.models import AccountAccess, Instance


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
