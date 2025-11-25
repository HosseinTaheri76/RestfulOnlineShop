from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from products.factories import (
    ProductFactory,
    ProductCategoryFactory,
    ProductTypeFactory,
    ProductBrandFactory,
)


class ProductCompareViewTests(TestCase):
    """
    Tests for the ProductCompareView endpoint.
    """

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("products:product-compare")

        self.category = ProductCategoryFactory(is_root=True)
        self.product_type = ProductTypeFactory(product_category=self.category, has_variants=False)
        self.brand = ProductBrandFactory()

        self.product1 = ProductFactory(
            product_category=self.category,
            product_type=self.product_type,
            product_brand=self.brand,
        )
        self.product2 = ProductFactory(
            product_category=self.category,
            product_type=self.product_type,
            product_brand=self.brand,
        )
        self.product3 = ProductFactory(
            product_category=self.category,
            product_type=self.product_type,
            product_brand=self.brand,
        )

    # ───────────────────────────────────────────────
    # ✅ Successful comparison
    # ───────────────────────────────────────────────
    def test_compare_multiple_products_returns_200(self):
        """
        Ensure comparing multiple valid products returns correct data.
        """
        response = self.client.get(
            self.url,
            {"product_ids": [self.product1.id, self.product2.id]},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertIn("products", data)
        self.assertEqual(len(data["products"]), 2)

        product_ids = [p["id"] for p in data["products"]]
        self.assertCountEqual(product_ids, [self.product1.id, self.product2.id])

    # ───────────────────────────────────────────────
    # 🚫 Missing query params
    # ───────────────────────────────────────────────
    def test_missing_product_ids_returns_400(self):
        """
        Omitting product_ids query params should raise a validation error.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ───────────────────────────────────────────────
    # 🚫 Only one product (should require at least 2)
    # ───────────────────────────────────────────────
    def test_single_product_id_returns_400(self):
        """
        The API should require at least two product IDs for comparison.
        """
        response = self.client.get(self.url, {"product_ids": [self.product1.id]})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ───────────────────────────────────────────────
    # 🚫 Nonexistent product IDs
    # ───────────────────────────────────────────────
    def test_nonexistent_product_ids_returns_400(self):
        """
        If one or more product IDs are invalid, serializer should raise validation error.
        """
        response = self.client.get(
            self.url,
            {"product_ids": [self.product1.id, 99999]},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ───────────────────────────────────────────────
    # 🧩 Duplicate product IDs
    # ───────────────────────────────────────────────
    def test_duplicate_product_ids_returns_400(self):
        """
        Duplicate product IDs should raise a validation error.
        """
        response = self.client.get(
            self.url,
            {"product_ids": [self.product1.id, self.product1.id]},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ───────────────────────────────────────────────
    # 🚫 Different product types
    # ───────────────────────────────────────────────
    def test_products_with_different_types_return_400(self):
        """
        Comparison should fail when products belong to different product types.
        """
        another_type = ProductTypeFactory(product_category=self.category)
        other_product = ProductFactory(
            product_type=another_type,
            product_category=self.category,
            product_brand=self.brand,
        )
        response = self.client.get(
            self.url,
            {"product_ids": [self.product1.id, other_product.id]},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
