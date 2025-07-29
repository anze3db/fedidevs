from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
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


class TestStarterPackAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create users and account access
        cls.user1 = baker.make("auth.User")
        cls.user2 = baker.make("auth.User")
        cls.account_access1 = baker.make("mastodon_auth.AccountAccess", user=cls.user1)
        cls.account_access2 = baker.make("mastodon_auth.AccountAccess", user=cls.user2)

        # Create instances for accounts
        cls.instance1 = baker.make("accounts.Instance")
        cls.instance2 = baker.make("accounts.Instance")

        # Create published starter packs
        cls.published_starter_pack1 = baker.make(
            "starter_packs.StarterPack",
            created_by=cls.user1,
            published_at=timezone.now(),
            title="Published Pack 1",
            description="Description for published pack 1",
            slug="published-pack-1",
        )
        cls.published_starter_pack2 = baker.make(
            "starter_packs.StarterPack",
            created_by=cls.user2,
            published_at=timezone.now(),
            title="Published Pack 2",
            description="Description for published pack 2",
            slug="published-pack-2",
        )

        # Create unpublished starter pack (should not appear in API)
        cls.unpublished_starter_pack = baker.make(
            "starter_packs.StarterPack",
            created_by=cls.user1,
            published_at=None,
            title="Unpublished Pack",
            description="Description for unpublished pack",
            slug="unpublished-pack",
        )

        # Create deleted starter pack (should not appear in API)
        cls.deleted_starter_pack = baker.make(
            "starter_packs.StarterPack",
            created_by=cls.user1,
            published_at=timezone.now(),
            deleted_at=timezone.now(),
            title="Deleted Pack",
            description="Description for deleted pack",
            slug="deleted-pack",
        )

        # Create accounts for starter packs
        cls.account1 = baker.make(
            "accounts.Account",
            discoverable=True,
            instance_model=cls.instance1,
            username="testuser1",
            display_name="Test User 1",
            account_id="account1",
        )
        cls.account2 = baker.make(
            "accounts.Account",
            discoverable=True,
            instance_model=cls.instance2,
            username="testuser2",
            display_name="Test User 2",
            account_id="account2",
        )
        cls.account3 = baker.make(
            "accounts.Account",
            discoverable=False,  # Not discoverable
            instance_model=cls.instance1,
            username="hiddenuser",
            display_name="Hidden User",
            account_id="account3",
        )

        # Add accounts to starter packs
        baker.make(
            "starter_packs.StarterPackAccount",
            starter_pack=cls.published_starter_pack1,
            account=cls.account1,
            created_by=cls.user1,
        )
        baker.make(
            "starter_packs.StarterPackAccount",
            starter_pack=cls.published_starter_pack1,
            account=cls.account2,
            created_by=cls.user1,
        )
        baker.make(
            "starter_packs.StarterPackAccount",
            starter_pack=cls.published_starter_pack1,
            account=cls.account3,  # Hidden account
            created_by=cls.user1,
        )

        baker.make(
            "starter_packs.StarterPackAccount",
            starter_pack=cls.published_starter_pack2,
            account=cls.account1,
            created_by=cls.user2,
        )

    def test_list_starter_packs_success(self):
        """Test that the API returns published starter packs correctly"""
        response = self.client.get("/api/starter-packs/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("items", data)
        self.assertIn("count", data)

        # Should contain 2 published starter packs
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["items"]), 2)

        # Check that starter packs are returned in order (newest first, by -id)
        starter_pack_slugs = [item["slug"] for item in data["items"]]
        self.assertIn("published-pack-1", starter_pack_slugs)
        self.assertIn("published-pack-2", starter_pack_slugs)

        # Verify structure of first starter pack
        first_pack = data["items"][0]
        self.assertIn("slug", first_pack)
        self.assertIn("description", first_pack)
        self.assertIn("published_at", first_pack)
        self.assertIn("updated_at", first_pack)
        self.assertIn("created_by", first_pack)
        self.assertIn("url", first_pack)
        self.assertIn("html_url", first_pack)

        # Check created_by structure
        created_by = first_pack["created_by"]
        self.assertIn("id", created_by)
        self.assertIn("username", created_by)
        self.assertIn("display_name", created_by)

        # Check URLs are properly formatted
        self.assertTrue(first_pack["url"].startswith("http"))
        self.assertTrue(first_pack["html_url"].startswith("http"))
        self.assertIn("/api/starter-packs/", first_pack["url"])
        self.assertIn("/s/", first_pack["html_url"])

    def test_list_starter_packs_pagination(self):
        """Test that pagination works correctly"""
        response = self.client.get("/api/starter-packs/?limit=1")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(len(data["items"]), 1)
        self.assertIn("next", data)
        self.assertIn("previous", data)

    def test_list_starter_packs_excludes_unpublished_and_deleted(self):
        """Test that unpublished and deleted starter packs are not included"""
        response = self.client.get("/api/starter-packs/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        starter_pack_slugs = [item["slug"] for item in data["items"]]

        # Should not include unpublished or deleted packs
        self.assertNotIn("unpublished-pack", starter_pack_slugs)
        self.assertNotIn("deleted-pack", starter_pack_slugs)

    def test_get_starter_pack_success(self):
        """Test retrieving a specific starter pack with accounts"""
        response = self.client.get(f"/api/starter-packs/{self.published_starter_pack1.slug}/")
        self.assertEqual(response.status_code, 200)

        data = response.json()

        # Check basic starter pack info
        self.assertEqual(data["slug"], self.published_starter_pack1.slug)
        self.assertEqual(data["description"], self.published_starter_pack1.description)
        self.assertIn("published_at", data)
        self.assertIn("created_by", data)
        self.assertIn("items", data)

        # Check that items (accounts) are included
        items = data["items"]
        self.assertIsInstance(items, list)

        # Should include discoverable accounts
        account_ids = [item["id"] for item in items]
        self.assertIn(self.account1.account_id, account_ids)
        self.assertIn(self.account2.account_id, account_ids)

        # Verify account structure
        first_account = items[0]
        self.assertIn("id", first_account)
        self.assertIn("username", first_account)
        self.assertIn("acct", first_account)
        self.assertIn("display_name", first_account)
        self.assertIn("locked", first_account)
        self.assertIn("bot", first_account)
        self.assertIn("discoverable", first_account)
        self.assertIn("followers_count", first_account)
        self.assertIn("following_count", first_account)
        self.assertIn("statuses_count", first_account)
        self.assertIn("url", first_account)
        self.assertIn("avatar", first_account)
        self.assertIn("header", first_account)
        self.assertIn("created_at", first_account)
        self.assertIn("note", first_account)

    def test_get_starter_pack_not_found(self):
        """Test retrieving a non-existent starter pack"""
        response = self.client.get("/api/starter-packs/non-existent-slug/")
        self.assertEqual(response.status_code, 404)

    def test_get_unpublished_starter_pack_not_found(self):
        """Test that unpublished starter packs return 404"""
        response = self.client.get(f"/api/starter-packs/{self.unpublished_starter_pack.slug}/")
        self.assertEqual(response.status_code, 404)

    def test_get_deleted_starter_pack_not_found(self):
        """Test that deleted starter packs return 404"""
        response = self.client.get(f"/api/starter-packs/{self.deleted_starter_pack.slug}/")
        self.assertEqual(response.status_code, 404)

    def test_get_starter_pack_includes_all_accounts(self):
        """Test that get starter pack includes all accounts, including non-discoverable ones"""
        response = self.client.get(f"/api/starter-packs/{self.published_starter_pack1.slug}/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        items = data["items"]

        # Should include all 3 accounts (including the non-discoverable one)
        self.assertEqual(len(items), 3)

        account_ids = [item["id"] for item in items]
        self.assertIn(self.account1.account_id, account_ids)
        self.assertIn(self.account2.account_id, account_ids)
        self.assertIn(self.account3.account_id, account_ids)  # Non-discoverable account

    def test_api_content_type_json(self):
        """Test that API returns JSON content type"""
        response = self.client.get("/api/starter-packs/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_api_response_structure_validation(self):
        """Test that API responses match expected schema structure"""
        # Test list endpoint structure
        response = self.client.get("/api/starter-packs/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        required_list_fields = ["items", "count", "next", "previous"]
        for field in required_list_fields:
            self.assertIn(field, data)

        if data["items"]:
            item = data["items"][0]
            required_item_fields = ["slug", "description", "published_at", "created_by", "url", "html_url"]
            for field in required_item_fields:
                self.assertIn(field, item)

        # Test detail endpoint structure
        response = self.client.get(f"/api/starter-packs/{self.published_starter_pack1.slug}/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        required_detail_fields = ["slug", "description", "published_at", "created_by", "url", "html_url", "items"]
        for field in required_detail_fields:
            self.assertIn(field, data)

    def test_created_by_user_data_structure(self):
        """Test that created_by user data has correct structure and data"""
        response = self.client.get(f"/api/starter-packs/{self.published_starter_pack1.slug}/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        created_by = data["created_by"]

        # Should include account data from AccountAccess
        self.assertEqual(created_by["id"], self.account_access1.account.account_id)
        self.assertEqual(created_by["username"], self.account_access1.account.username)
        self.assertEqual(created_by["display_name"], self.account_access1.account.display_name)

        # Check that all required fields are present
        required_fields = [
            "id",
            "username",
            "acct",
            "locked",
            "bot",
            "discoverable",
            "group",
            "created_at",
            "note",
            "url",
            "avatar",
            "avatar_static",
            "header",
            "header_static",
            "followers_count",
            "following_count",
            "statuses_count",
            "display_name",
            "fields",
            "emojis",
        ]
        for field in required_fields:
            self.assertIn(field, created_by)
