import xml.etree.ElementTree as ET

from django.core import management
from django.test import TestCase
from django.utils import timezone

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
        response = self.client.get("/")
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
        response = self.client.get("/")
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
