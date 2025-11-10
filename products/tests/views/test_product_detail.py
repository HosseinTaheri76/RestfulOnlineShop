from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from products import factories


class ProductDetailViewTests(TestCase):
    """
    Tests for ProductDetailView (RetrieveAPIView).
    """

    def setUp(self):
        self.client = APIClient()

        # Create category
        self.category = factories.ProductCategoryFactory(title="Phones",slug="phones",is_active=True)
        self.type = factories.ProductTypeFactory(title="Phone", has_variants=True, product_category=self.category)
        # Create product
        self.product = factories.ProductFactory(
            title="iPhone 16",
            slug="iphone-16",
            product_type=self.type,
            product_category=self.category,
            is_active=True,
            description="Next-gen iPhone",
        )

        # Create primary variant (SKU)
        self.sku = factories.ProductVariantFactory(
            product=self.product,
            sku="IPH16-BLK-128",
            is_primary=True,
            price=999,
        )

        # Create some stock for SKU
        self.stock = factories.ProductStockFactory(
            product=self.product,
            product_variant=self.sku,
            quantity=5,
            reserved=1,
        )

        # Create an attribute (e.g., color)
        self.attribute = factories.ProductAttributeFactory(
            title="Color",
            filterable=True,
        )
        self.ta = factories.ProductTypeAttributeFactory(product_type=self.type, product_attribute=self.attribute)

        self.option_black = factories.ProductAttributeOptionFactory(
            product_attribute=self.attribute,
            value="Black",
        )

        # Link attribute to type or product depending on your schema
        # Assuming you use ProductSKUAttributeValue model
        self.attr_value = factories.ProductSKUAttributeValueFactory(
            product=self.product,
            product_variant=self.sku,
            product_type_attribute=self.ta,
            value=self.option_black,
        )

        # Build the product detail URL
        self.url = reverse(
            "products:product-detail",  # change to your actual route name if needed
            kwargs={"product_slug": self.product.slug},
        )

    def test_retrieve_existing_product(self):
        """Should return details for a valid product slug."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Core product fields
        self.assertEqual(data["title"], "iPhone 16")

        # Check variants
        variants = data.get("variants", [])
        self.assertTrue(any(v["sku"] == "IPH16-BLK-128" for v in variants))

        # Check that attribute values are serialized
        attributes = data.get("attributes", [])
        if attributes:
            self.assertIn("Color", [a["attribute"]["name"] for a in attributes])

    def test_product_not_found_returns_404(self):
        """Should return 404 if slug does not exist."""
        url = reverse("products:product-detail", kwargs={"product_slug": "nonexistent"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

