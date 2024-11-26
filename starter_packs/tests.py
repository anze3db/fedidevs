from django.test import TestCase
from django.urls import reverse
from model_bakery import baker


class TestStarterPacks(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("starter_packs.StarterPack", _quantity=5)

    def test_index_page(self):
        response = self.client.get(reverse("starter_packs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Community Starter Packs")
        self.assertNotContains(response, "Your Starter Packs")

    def test_index_page_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("starter_packs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Community Starter Packs")
        self.assertNotContains(response, "Your Starter Packs")

    def test_index_page_with_own_starter_packs(self):
        baker.make("starter_packs.StarterPack", created_by=self.user, _quantity=2)
        self.client.force_login(self.user)
        response = self.client.get(reverse("starter_packs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Starter Packs")
        self.assertContains(response, "Community Starter Packs")


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
