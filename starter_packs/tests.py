from ddt import data, ddt, unpack
from django.test import TestCase
from django.urls import reverse
from model_bakery import baker

from accounts.models import Account
from starter_packs.models import StarterPackAccount


class TestStarterPacks(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("starter_packs.StarterPack", _quantity=5)

    def test_index_page(self):
        response = self.client.get(reverse("starter_packs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Community Starter Packs")
        self.assertContains(response, "Your Starter Packs")
        self.assertContains(response, "Starter Packs Containing You")

    def test_index_page_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("starter_packs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Community Starter Packs")
        self.assertContains(response, "Your Starter Packs")
        self.assertContains(response, "Starter Packs Containing You")

    def test_index_page_with_own_starter_packs(self):
        baker.make("starter_packs.StarterPack", created_by=self.user, _quantity=2)
        self.client.force_login(self.user)
        response = self.client.get(reverse("starter_packs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Starter Packs")
        self.assertContains(response, "Your Starter Packs")
        self.assertContains(response, "Starter Packs Containing You")


class TestCreateStarterPack(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.user)

    def test_create_page(self):
        response = self.client.get(reverse("create_starter_pack"))
        self.assertRedirects(response, reverse("login") + "?next=/starter-packs/create/")

    def test_create_page_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("create_starter_pack"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mastodon starter packs")

    def test_create_starter_pack(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("create_starter_pack"),
            {
                "title": "Test Starter Pack",
                "description": "This is a test starter pack",
            },
        )
        starter_pack = self.user.starterpack_set.first()
        self.assertEqual(starter_pack.created_by, self.user)
        self.assertRedirects(response, reverse("edit_accounts_starter_pack", args=[starter_pack.slug]))

    def test_form_error(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("create_starter_pack"), {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertEqual(self.user.starterpack_set.count(), 0)


class TestEditStarterPack(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.user)
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.user)

    def test_not_logged_in(self):
        response = self.client.get(reverse("edit_starter_pack", args=[self.starter_pack.slug]))
        self.assertRedirects(response, reverse("login") + f"?next=/starter-packs/{self.starter_pack.slug}/edit/")

    def test_not_owned_starter_pack(self):
        other_user = baker.make("auth.User")
        self.client.force_login(other_user)
        response = self.client.get(reverse("edit_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 404)

    def test_edit_starter_packs(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("edit_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mastodon starter packs")
        self.assertContains(response, self.starter_pack.title)
        self.assertContains(response, self.starter_pack.description)

    def test_edit_starter_pack_post(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("edit_starter_pack", args=[self.starter_pack.slug]),
            {
                "title": "New title",
                "description": "New description",
            },
        )
        self.starter_pack.refresh_from_db()
        self.assertEqual(self.starter_pack.title, "New title")
        self.assertEqual(self.starter_pack.description, "New description")
        self.assertRedirects(response, reverse("edit_accounts_starter_pack", args=[self.starter_pack.slug]))


class TestEditStarterPackAccounts(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.user)
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.user)

    def test_not_logged_in(self):
        response = self.client.get(reverse("edit_accounts_starter_pack", args=[self.starter_pack.slug]))
        self.assertRedirects(
            response, reverse("login") + f"?next=/starter-packs/{self.starter_pack.slug}/edit/accounts/"
        )

    def test_not_owned_starter_pack(self):
        other_user = baker.make("auth.User")
        self.client.force_login(other_user)
        response = self.client.get(reverse("edit_accounts_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 404)

    def test_edit_starter_packs(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("edit_accounts_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search @username@instance.org")


class TestDeleteStarterPack(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.user)
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.user)

    def test_not_logged_in(self):
        response = self.client.get(reverse("delete_starter_pack", args=[self.starter_pack.slug]))
        self.assertRedirects(response, reverse("login") + f"?next=/starter-packs/{self.starter_pack.slug}/delete/")

    def test_not_owned_starter_pack(self):
        other_user = baker.make("auth.User")
        self.client.force_login(other_user)
        response = self.client.get(reverse("delete_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 404)

    def test_delete_confirmation(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("delete_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, f'Are you sure you want to delete the starter pack <strong>"{self.starter_pack.title}"</strong>?'
        )

    def test_delete(self):
        self.client.force_login(self.user)
        self.assertIsNone(self.starter_pack.deleted_at)
        response = self.client.post(reverse("delete_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 302)
        self.starter_pack.refresh_from_db()
        self.assertIsNotNone(self.starter_pack.deleted_at)


class TestToggleStarterPackAccount(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.user)
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.user)

    def test_add_account(self):
        account = baker.make("accounts.Account", discoverable=True)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "toggle_account_to_starter_pack",
                kwargs={"starter_pack_slug": self.starter_pack.slug, "account_id": account.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            StarterPackAccount.objects.filter(
                account_id=account.id, starter_pack_id=self.starter_pack.id, created_by=self.user
            ).exists()
        )

    def test_remove_account(self):
        account = baker.make("accounts.Account", discoverable=True)
        self.client.force_login(self.user)
        baker.make("starter_packs.StarterPackAccount", account=account, starter_pack=self.starter_pack)
        response = self.client.post(
            reverse(
                "toggle_account_to_starter_pack",
                kwargs={"starter_pack_slug": self.starter_pack.slug, "account_id": account.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            StarterPackAccount.objects.filter(account_id=account.id, starter_pack_id=self.starter_pack.id).exists()
        )

    def test_toggle_after_limit(self):
        account = baker.make("accounts.Account", discoverable=True)
        self.client.force_login(self.user)
        # baker.make("starter_packs.StarterPackAccount", starter_pack=self.starter_pack, account=account)
        baker.make("starter_packs.StarterPackAccount", starter_pack=self.starter_pack, _quantity=150)

        self.assertEqual(self.starter_pack.starterpackaccount_set.count(), 150)
        response = self.client.post(
            reverse(
                "toggle_account_to_starter_pack",
                kwargs={"starter_pack_slug": self.starter_pack.slug, "account_id": account.id},
            )
        )
        self.assertEqual(response.status_code, 200)

        # Make sure we can delete even after the limit:
        baker.make("starter_packs.StarterPackAccount", starter_pack=self.starter_pack, account=account)
        self.assertEqual(self.starter_pack.starterpackaccount_set.count(), 151)
        response = self.client.post(
            reverse(
                "toggle_account_to_starter_pack",
                kwargs={"starter_pack_slug": self.starter_pack.slug, "account_id": account.id},
            )
        )
        self.assertEqual(self.starter_pack.starterpackaccount_set.count(), 150)


@ddt
class TestShareStarterPack(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make(
            "mastodon_auth.AccountAccess",
            user=cls.user,
            account__activitypub_id="https://instance.org/users/createdbyuser",
        )
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.user, num_accounts=5)
        instance = baker.make("accounts.Instance")
        baker.make(
            "starter_packs.StarterPackAccount",
            starter_pack=cls.starter_pack,
            account__discoverable=True,
            account__instance_model=instance,
            account__activitypub_id="https://instance.org/users/user",
            _quantity=5,
        )

    def test_not_existing_starter_pack(self):
        response = self.client.get(reverse("share_starter_pack", args=["not-existing"]))
        self.assertEqual(response.status_code, 404)

    def test_share_starter_pack(self):
        response = self.client.get(reverse("share_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.starter_pack.title)
        self.assertContains(response, self.starter_pack.description)

        for account in self.starter_pack.starterpackaccount_set.all():
            with self.subTest("Check account"):
                self.assertContains(response, account.account.username)

        self.assertNotContains(response, "Edit")
        self.assertNotContains(response, "Delete")
        self.assertContains(response, "Follow all 5 accounts")

    def test_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("share_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.starter_pack.title)
        self.assertContains(response, self.starter_pack.description)

        for account in self.starter_pack.starterpackaccount_set.all():
            with self.subTest("Check account"):
                self.assertContains(response, account.account.username)

        self.assertContains(response, "Edit")
        self.assertContains(response, "Delete")
        self.assertContains(response, "Follow all 5 accounts")

    def test_non_discoverable_accounts(self):
        Account.objects.update(discoverable=False)
        self.starter_pack.num_accounts = 0
        self.starter_pack.save()
        response = self.client.get(reverse("share_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.starter_pack.title)
        self.assertContains(response, self.starter_pack.description)

        for account in self.starter_pack.starterpackaccount_set.all():
            with self.subTest("Check account"):
                self.assertNotContains(response, account.account.username)

        self.assertNotContains(response, "Edit")
        self.assertNotContains(response, "Delete")
        self.assertNotContains(response, "Follow all 5 accounts")

    @data(
        # ActivityPub:
        ('application/ld+json; profile="https://www.w3.org/ns/activitystreams"', "application/activity+json"),  # MUST
        ("application/activity+json", "application/activity+json"),  # SHOULD
        ("application/activity+json;q=0.5,text/html;q=0.4", "application/activity+json"),
        # JSON:
        ("application/json", "application/json"),
        ("application/json;q=0.5,text/html;q=0.4", "application/json"),
        # HTML:
        ("text/html", "text/html"),
        ("text/plain", "text/html"),
    )
    @unpack
    def test_api_formats(self, accept_header, expected_content_type):
        # Testing the content negotiation. See: https://www.w3.org/TR/activitypub/#retrieving-objects
        response = self.client.get(
            reverse("share_starter_pack", args=[self.starter_pack.slug]),
            headers={"accept": accept_header},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"].split(";")[0], expected_content_type)

    def test_api_plain_json(self):
        # Testing the plain JSON response
        url = reverse("share_starter_pack", args=[self.starter_pack.slug])
        response = self.client.get(
            url,
            headers={"accept": "application/json"},
        )

        payload = response.json()
        accounts = (
            Account.objects.filter(
                starterpackaccount__starter_pack=self.starter_pack,
                instance_model__isnull=False,
                instance_model__deleted_at__isnull=True,
                discoverable=True,
            )
            .select_related("accountlookup", "instance_model")
            .order_by("-followers_count")
        )
        self.assertEqual(
            payload,
            {
                "url": f"http://testserver{url}",
                "title": self.starter_pack.title,
                "description": self.starter_pack.description,
                "created_by": self.starter_pack.created_by.username,
                "created_at": self.starter_pack.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "updated_at": self.starter_pack.updated_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "published_at": self.starter_pack.published_at,
                "daily_follows": self.starter_pack.daily_follows,
                "weekly_follows": self.starter_pack.weekly_follows,
                "monthly_follows": self.starter_pack.monthly_follows,
                "accounts": [
                    {
                        "name": account.name,
                        "handle": account.username_at_instance,
                        "url": account.url,
                        "activitypub_id": account.activitypub_id,
                        "created_at": account.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                        "followers_count": account.followers_count,
                        "following_count": account.following_count,
                        "statuses_count": account.statuses_count,
                        "bot": account.bot,
                        "discoverable": account.discoverable,
                        "locked": account.locked,
                        "noindex": account.noindex,
                        "avatar": account.avatar,
                        "header": account.avatar,
                    }
                    for account in accounts
                ],
            },
        )

    def test_api_activitypub(self):
        # Testing the ActivityPub response
        url = reverse("share_starter_pack", args=[self.starter_pack.slug])
        response = self.client.get(
            url,
            headers={"accept": 'application/ld+json; profile="https://www.w3.org/ns/activitystreams"'},
        )

        # ActivityPub is kind of difficult to test for syntactically, but these will always be in there:
        self.assertContains(response, '"@context"')
        self.assertContains(response, '"https://www.w3.org/ns/activitystreams"')
        payload = response.json()

        accounts = (
            Account.objects.filter(
                starterpackaccount__starter_pack=self.starter_pack,
                instance_model__isnull=False,
                instance_model__deleted_at__isnull=True,
                discoverable=True,
            )
            .select_related("accountlookup", "instance_model")
            .order_by("-followers_count")
        )

        expected_payload = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Collection",
            "id": f"http://testserver{url}",
            "name": self.starter_pack.title,
            "summary": self.starter_pack.description,
            "attributedTo": self.starter_pack.created_by.accountaccess.account.activitypub_id,
            "published": self.starter_pack.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "updated": self.starter_pack.updated_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "image": {
                "type": "Image",
                "mediaType": "image/png",
                "url": payload["image"]["url"],
                "summary": "",
            },
            "generator": {
                "type": "Application",
                "name": "Fedidevs",
                "url": "http://testserver/",
            },
            "totalItems": accounts.count(),
            "items": [account.activitypub_id for account in accounts],
        }

        self.assertEqual(payload, expected_payload)
