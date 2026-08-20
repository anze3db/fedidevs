from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TestCase


def _vary_tokens(response) -> set[str]:
    vary = response.get("Vary") or ""
    return {header.strip().lower() for header in vary.split(",") if header.strip()}


class TestRobotsTxt(SimpleTestCase):
    def test_disallows_query_strings(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertIn("Disallow: /*?", response.content.decode())
        self.assertIn("Sitemap: https://fedidevs.com/sitemap.xml", response.content.decode())


class TestCanonicalQueryParams(SimpleTestCase):
    def test_unknown_root_param_is_301ed(self):
        response = self.client.get("/?amp=1")
        self.assertRedirects(response, "/", status_code=301, fetch_redirect_response=False)

    def test_unknown_param_is_stripped_from_faceted_url(self):
        response = self.client.get("/?q=python&amp=1&utm_source=bot")
        self.assertRedirects(response, "/?q=python", status_code=301, fetch_redirect_response=False)

    def test_empty_q_is_preserved(self):
        response = self.client.get("/?q=&amp=1")
        self.assertRedirects(response, "/?q=", status_code=301, fetch_redirect_response=False)

    def test_starter_pack_and_oauth_params_are_kept(self):
        response = self.client.get("/starter-packs/?tab=your&amp=1")
        self.assertRedirects(
            response,
            "/starter-packs/?tab=your",
            status_code=301,
            fetch_redirect_response=False,
        )
        response = self.client.get("/mastodon_auth/?code=abc&state=xyz&amp=1")
        self.assertRedirects(
            response,
            "/mastodon_auth/?code=abc&state=xyz",
            status_code=301,
            fetch_redirect_response=False,
        )


class TestAnonymousCacheAndCsrf(TestCase):
    def test_known_params_are_not_redirected(self):
        response = self.client.get("/login/?q=python")
        self.assertEqual(response.status_code, 200)

    def test_admin_query_params_are_left_alone(self):
        response = self.client.get("/admin/?foo=bar")
        self.assertNotEqual(response.status_code, 301)

    def test_anonymous_html_is_publicly_cacheable_without_csrf_cookie(self):
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("public", response["Cache-Control"])
        self.assertIn("s-maxage=300", response["Cache-Control"])
        self.assertNotIn("cookie", _vary_tokens(response))
        self.assertNotIn(settings.CSRF_COOKIE_NAME, response.cookies)
        self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)
        self.assertContains(response, 'data-csrf-url="/csrf/"')
        self.assertNotContains(response, "X-CSRFToken")

    def test_authenticated_html_is_private_and_keeps_csrf_header(self):
        User.objects.create_user("alice", password="pw")
        self.client.login(username="alice", password="pw")
        response = self.client.get("/conferences/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("private", response["Cache-Control"])
        self.assertContains(response, "X-CSRFToken")
        self.assertNotContains(response, "data-csrf-url")

    def test_csrf_endpoint_sets_cookie_and_returns_token(self):
        response = self.client.get("/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("csrfToken", response.json())
        self.assertTrue(response.json()["csrfToken"])
        self.assertIn(settings.CSRF_COOKIE_NAME, response.cookies)

    def test_anonymous_post_without_csrf_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.get("/login/")
        response = client.post("/i18n/setlang/", {"language": "de", "next": "/login/"})
        self.assertEqual(response.status_code, 403)

    def test_anonymous_forms_work_after_csrf_bootstrap(self):
        client = Client(enforce_csrf_checks=True)
        # Cached anonymous GET must not mint a CSRF cookie.
        page = client.get("/login/")
        self.assertNotIn(settings.CSRF_COOKIE_NAME, page.cookies)

        token = client.get("/csrf/").json()["csrfToken"]
        response = client.post(
            "/i18n/setlang/",
            {"language": "de", "next": "/login/", "csrfmiddlewaretoken": token},
        )
        self.assertEqual(response.status_code, 302)

        subscribe = client.post(
            "/posts/subscribe",
            {"email": "cache-test@example.com", "csrfmiddlewaretoken": token},
        )
        self.assertNotEqual(subscribe.status_code, 403)

    def test_faceted_pages_are_noindex_with_canonical(self):
        response = self.client.get("/login/?q=")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="robots"')
        self.assertContains(response, "noindex")
        self.assertContains(response, 'rel="canonical" href="https://fedidevs.com/login/"')

    def test_plain_pages_are_indexable(self):
        response = self.client.get("/login/")
        self.assertNotContains(response, 'name="robots"')


class TestConnMaxAge(SimpleTestCase):
    def test_postgres_reuses_connections(self):
        engine = settings.DATABASES["default"]["ENGINE"]
        if "sqlite" in engine:
            self.assertEqual(settings.DATABASES["default"]["CONN_MAX_AGE"], 0)
            return
        self.assertGreater(settings.DATABASES["default"]["CONN_MAX_AGE"], 0)
        self.assertTrue(settings.DATABASES["default"]["CONN_HEALTH_CHECKS"])
