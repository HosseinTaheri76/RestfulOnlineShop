from django.urls import reverse
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from products import models, factories


class CategoryListViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.parent = factories.ProductCategoryFactory()
        self.child = factories.ProductCategoryFactory(is_root=False, parent=self.parent)
        self.url = reverse("products:category-list")  # adjust name according to your urls.py

    def test_returns_all_categories(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data[0]['title'] == self.parent.title)
        self.assertTrue(data[0]['sub_categories'][0]['title'] == self.child.title)

    def test_returns_empty_when_no_active_categories(self):
        models.ProductCategory.objects.all().update(is_active=False)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), [])
