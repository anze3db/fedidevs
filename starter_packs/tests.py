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


class TestShareStarterPack(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.user)
        # FIXME: setup for ActivityPub tests
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.user)
        instance = baker.make("accounts.Instance")
        baker.make(
            "starter_packs.StarterPackAccount",
            starter_pack=cls.starter_pack,
            account__discoverable=True,
            account__instance_model=instance,
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

    def test_activitypub(self):
        # Testing the content negotiation. See: https://www.w3.org/TR/activitypub/#retrieving-objects
        accept_activitypub = (
            'application/ld+json; profile="https://www.w3.org/ns/activitystreams"',  # MUST
            "application/activity+json",  # SHOULD
            "application/activity+json;q=0.5,text/html;q=0.4",
        )
        accept_json = (
            "application/json",
            "application/json;q=0.5,text/html;q=0.4",
        )
        accept_html = (
            "text/html",
            "text/plain",
            "application/activity+json;q=0.4,text/html;q=0.5",
        )
        for accept in accept_activitypub + accept_json + accept_html:
            response = self.client.get(
                reverse("share_starter_pack", args=[self.starter_pack.slug]),
                headers={"accept": accept},
            )
            self.assertEqual(response.status_code, 200)
            if accept in accept_activitypub:
                self.assertEqual(response.headers["Content-Type"].split(";")[0], "application/activity+json")
            elif accept in accept_json:
                self.assertEqual(response.headers["Content-Type"].split(";")[0], "application/json")
            else:
                self.assertEqual(response.headers["Content-Type"].split(";")[0], "text/html")

        # Testing the plain JSON response
        response = self.client.get(
            reverse("share_starter_pack", args=[self.starter_pack.slug]),
            headers={"accept": "application/json"},
        )

        payload = response.json()
        self.assertIn("title", payload)
        self.assertIsInstance(payload["title"], str)
        self.assertIn("description", payload)
        self.assertIsInstance(payload["description"], str)
        self.assertIn("url", payload)
        self.assertIsInstance(payload["url"], str)
        self.assertIn("accounts", payload)
        self.assertIsInstance(payload["accounts"], list)

        # Testing the ActivityPub response
        response = self.client.get(
            reverse("share_starter_pack", args=[self.starter_pack.slug]),
            headers={"accept": 'application/ld+json; profile="https://www.w3.org/ns/activitystreams"'},
        )

        # ActivityPub is kind of difficult to test for syntactically, but these will always be in there:
        self.assertContains(response, '"@context"')
        self.assertContains(response, '"https://www.w3.org/ns/activitystreams"')
        payload = response.json()
        self.assertIn("@context", payload)
        self.assertIsInstance(payload.get("id"), str)

        # From here we test for compliance with the starter kit schema.
        # See https://github.com/pixelfed/starter-kits/issues/1
        self.assertIn(payload.get("type"), ["Collection", "OrderedCollection"])
        self.assertIsInstance(payload.get("name"), str)
        self.assertIsInstance(payload.get("summary"), str)
        self.assertIsInstance(payload.get("totalItems"), int)
        items = None
        if payload.get("type") == "Collection":
            items = payload.get("items")
        if payload.get("type") == "OrderedCollection":
            items = payload.get("orderedItems")
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), payload.get("totalItems"))
