from unittest.mock import patch

from django.contrib.messages import get_messages
from django.test import TestCase

from mastodon_auth.forms import MastodonLoginForm


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
