from unittest import mock

import psycopg
from django.conf import settings
from django.contrib.auth.models import User
from django.db.backends.postgresql.base import DatabaseWrapper as PostgresDatabaseWrapper
from django.test import Client, SimpleTestCase, TestCase
from model_bakery import baker

from fedidevs.db.postgresql.base import DatabaseWrapper


def _vary_tokens(response) -> set[str]:
    vary = response.get("Vary") or ""
    return {header.strip().lower() for header in vary.split(",") if header.strip()}


class TestRobotsTxt(SimpleTestCase):
    def test_disallows_query_strings_except_googlebot(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
        body = response.content.decode()
        self.assertIn("User-agent: Googlebot", body)
        self.assertIn("Allow: /", body)
        self.assertIn("Disallow: /*?", body)
        self.assertIn("Sitemap: https://fedidevs.com/sitemap.xml", body)


class TestAccountIndexQueryParams(SimpleTestCase):
    def test_unknown_root_param_is_301ed(self):
        response = self.client.get("/?amp=1")
        self.assertRedirects(response, "/", status_code=301, fetch_redirect_response=False)

    def test_unknown_param_is_stripped_from_faceted_url(self):
        response = self.client.get("/?q=python&amp=1&utm_source=bot")
        self.assertRedirects(response, "/?q=python", status_code=301, fetch_redirect_response=False)

    def test_empty_q_is_preserved(self):
        response = self.client.get("/?q=&amp=1")
        self.assertRedirects(response, "/?q=", status_code=301, fetch_redirect_response=False)

    def test_language_index_strips_unknown_params(self):
        response = self.client.get("/python/?amp=1")
        self.assertRedirects(response, "/python/", status_code=301, fetch_redirect_response=False)


class TestAnonymousCacheAndCsrf(TestCase):
    def test_other_pages_keep_unknown_query_params(self):
        response = self.client.get("/login/?amp=1")
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/starter-packs/?amp=1")
        self.assertNotEqual(response.status_code, 301)
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

    def test_query_string_pages_are_not_noindexed(self):
        response = self.client.get("/login/?q=")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="robots"')
        self.assertContains(response, 'rel="canonical" href="https://fedidevs.com/login/"')

    def test_plain_pages_are_indexable(self):
        response = self.client.get("/login/")
        self.assertNotContains(response, 'name="robots"')


class TestPotatoqDashboard(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make(User)
        cls.staff = baker.make(User, is_staff=True)
        cls.superuser = baker.make(User, is_superuser=True, is_staff=False)
        cls.inactive_staff = baker.make(User, is_staff=True, is_active=False)

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get("/potatoq/")
        self.assertRedirects(response, "/login/?next=/potatoq/", fetch_redirect_response=False)

    def test_regular_user_is_forbidden(self):
        self.client.force_login(self.user)
        response = self.client.get("/potatoq/")
        self.assertEqual(response.status_code, 403)

    def test_inactive_staff_is_treated_as_logged_out(self):
        self.client.force_login(self.inactive_staff)
        response = self.client.get("/potatoq/")
        self.assertRedirects(response, "/login/?next=/potatoq/", fetch_redirect_response=False)

    def test_staff_sees_dashboard(self):
        self.client.force_login(self.staff)
        response = self.client.get("/potatoq/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<script src="app.js" defer></script>')
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_superuser_without_staff_flag_sees_dashboard(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/potatoq/app.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/javascript; charset=utf-8")

    def test_actions_skip_django_csrf_but_need_dashboard_header(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        response = client.post("/potatoq/api/tasks/some-task/revoke")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "Actions must come from the dashboard page"})


class TestRetryingPostgresBackend(SimpleTestCase):
    def setUp(self):
        self.wrapper = DatabaseWrapper(
            {
                "ENGINE": "fedidevs.db.postgresql",
                "NAME": "fedidevs",
                "USER": "",
                "PASSWORD": "",
                "HOST": "",
                "PORT": "",
                "OPTIONS": {},
                "TIME_ZONE": None,
                "CONN_MAX_AGE": 0,
                "CONN_HEALTH_CHECKS": True,
                "AUTOCOMMIT": True,
                "ATOMIC_REQUESTS": False,
                "TEST": {},
            }
        )

    def test_conn_health_checks_enabled(self):
        self.assertIs(settings.DATABASES["default"]["CONN_HEALTH_CHECKS"], True)

    def test_postgres_engine_is_swapped_for_the_retrying_one(self):
        engine = settings.DATABASES["default"]["ENGINE"]
        self.assertNotEqual(engine, "django.db.backends.postgresql")
        # potatoq detects Postgres with ENGINE.endswith("postgresql")
        if "postgresql" in engine:
            self.assertEqual(engine, "fedidevs.db.postgresql")

    @mock.patch("fedidevs.db.postgresql.base.time.sleep")
    def test_retries_while_postgres_is_unavailable(self, sleep):
        connection = object()
        refused = psycopg.OperationalError('connection failed: connect to server at "127.0.0.1": Connection refused')
        with (
            mock.patch.object(
                PostgresDatabaseWrapper, "get_new_connection", side_effect=[refused, refused, connection]
            ) as parent,
            self.assertLogs("fedidevs.db.postgresql.base", level="WARNING"),
        ):
            self.assertIs(self.wrapper.get_new_connection({}), connection)
        self.assertEqual(parent.call_count, 3)
        self.assertEqual(sleep.call_args_list, [mock.call(0.5), mock.call(1)])

    @mock.patch("fedidevs.db.postgresql.base.time.sleep")
    def test_gives_up_after_the_last_retry(self, sleep):
        shutting_down = psycopg.OperationalError("FATAL:  the database system is shutting down")
        with (
            mock.patch.object(PostgresDatabaseWrapper, "get_new_connection", side_effect=shutting_down) as parent,
            self.assertLogs("fedidevs.db.postgresql.base", level="WARNING"),
            self.assertRaises(psycopg.OperationalError),
        ):
            self.wrapper.get_new_connection({})
        self.assertEqual(parent.call_count, 6)
        self.assertEqual(sleep.call_args_list, [mock.call(d) for d in (0.5, 1, 2, 4, 8)])

    @mock.patch("fedidevs.db.postgresql.base.time.sleep")
    def test_does_not_retry_other_errors(self, sleep):
        bad_password = psycopg.OperationalError('FATAL:  password authentication failed for user "fedidevs"')
        with (
            mock.patch.object(PostgresDatabaseWrapper, "get_new_connection", side_effect=bad_password) as parent,
            self.assertRaises(psycopg.OperationalError),
        ):
            self.wrapper.get_new_connection({})
        self.assertEqual(parent.call_count, 1)
        sleep.assert_not_called()
