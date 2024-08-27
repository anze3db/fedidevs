# from django.test import TestCase

# Create your tests hereo

from django.test import TestCase


class TestConferencePage(TestCase):
    def test_conferences_page(self):
        response = self.client.get("/conferences/")
        self.assertEqual(response.status_code, 200)
