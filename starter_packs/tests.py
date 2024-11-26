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

    def test_create_page(self):
        response = self.client.get(reverse("create_starter_pack"))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("login") + "?next=/starter-packs/create/")

