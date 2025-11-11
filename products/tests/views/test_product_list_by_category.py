from django.urls import reverse
from django.db.models import Min, Max
from django.test import TestCase
from rest_framework.test import APIClient

from products import models, factories


class ProductListByCategoryViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create a root category and one subcategory
        self.category = factories.ProductCategoryFactory(is_root=True)
        self.subcategory = factories.ProductCategoryFactory(parent=self.category, is_root=False)

        # Create a product type
        self.product_type = factories.ProductTypeFactory(product_category=self.subcategory, has_variants=True)

        # Create a few products in this category
        self.product1 = factories.ProductFactory(
            product_category=self.subcategory,
            product_type=self.product_type,
        )
        self.product_1_primary_variant = factories.ProductVariantFactory(
            product=self.product1,
            price=1000,
        )

        self.product2 = factories.ProductFactory(
            product_category=self.subcategory,
            product_type=self.product_type,
        )
        self.product_2_primary_variant = factories.ProductVariantFactory(
            product=self.product2,
            price=2000,
        )

        # Create stocks (both available)
        factories.ProductStockFactory(
            product_variant=self.product_1_primary_variant,
            product=self.product1,
            quantity=10,
            reserved=2
        )
        factories.ProductStockFactory(
            product_variant=self.product_2_primary_variant,
            product=self.product2,
            quantity=5,
            reserved=0
        )

        # Add filterable attributes
        self.attr_color = factories.ProductAttributeFactory(
            title="Color",
            filterable=True,
            scope=models.ProductAttribute.Scope.VARIANT
        )
        self.attr_storage = factories.ProductAttributeFactory(
            title="Storage",
            filterable=True,
            scope=models.ProductAttribute.Scope.VARIANT
        )

        # Link attributes to product type
        self.ta_color = factories.ProductTypeAttributeFactory(
            product_type=self.product_type,
            product_attribute=self.attr_color
        )
        self.ta_storage = factories.ProductTypeAttributeFactory(
            product_type=self.product_type,
            product_attribute=self.attr_storage
        )

        # Create attribute options
        self.red = factories.ProductAttributeOptionFactory(product_attribute=self.attr_color, value="Red")
        self.blue = factories.ProductAttributeOptionFactory(product_attribute=self.attr_color, value="Blue")
        self.storage_128 = factories.ProductAttributeOptionFactory(product_attribute=self.attr_storage, value="128GB")
        self.storage_256 = factories.ProductAttributeOptionFactory(product_attribute=self.attr_storage, value="256GB")

        # Attach attributes to products
        factories.ProductSKUAttributeValueFactory(
            product=self.product1,
            product_variant=self.product_1_primary_variant,
            product_type_attribute=self.ta_color,
            value=self.red
        )
        factories.ProductSKUAttributeValueFactory(
            product=self.product1,
            product_variant=self.product_1_primary_variant,
            product_type_attribute=self.ta_storage,
            value=self.storage_128
        )
        factories.ProductSKUAttributeValueFactory(
            product=self.product2,
            product_variant=self.product_2_primary_variant,
            product_type_attribute=self.ta_color,
            value=self.blue
        )
        factories.ProductSKUAttributeValueFactory(
            product=self.product2,
            product_variant=self.product_2_primary_variant,
            product_type_attribute=self.ta_storage,
            value=self.storage_256
        )

        self.url = reverse("products:product-list-by-category", kwargs={"product_category_slug": self.subcategory.slug})

    def test_returns_products_within_category(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        product_titles = [p["title"] for p in data["products"]["results"]]
        self.assertIn(self.product1.title, product_titles)
        self.assertIn(self.product2.title, product_titles)

    def test_includes_min_and_max_price(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(float(data["min_price"]), float(1000))
        self.assertEqual(float(data["max_price"]), float(2000))

    def test_returns_filterable_attributes_for_category(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        filters = response.json()["filters"]

        titles = [f["title"] for f in filters]
        self.assertIn("Color", titles)
        self.assertIn("Storage", titles)

    def test_filters_by_attribute_value(self):
        """Ensure that filtering by attribute values works (attr<id>=<option_id>)."""
        query = f"?attr{self.attr_color.id}={self.red.id}"
        response = self.client.get(self.url + query)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        product_titles = [p["title"] for p in data["products"]["results"]]
        self.assertIn(self.product1.title, product_titles)
        self.assertNotIn(self.product2.title, product_titles)

    def test_filters_ignore_non_filterable_attributes(self):
        """If user sends attr with a non-filterable attribute, it should be ignored."""
        non_filterable_attr = factories.ProductAttributeFactory(filterable=False)
        option = factories.ProductAttributeOptionFactory(product_attribute=non_filterable_attr)

        query = f"?attr{non_filterable_attr.id}={option.id}"
        response = self.client.get(self.url + query)
        self.assertEqual(response.status_code, 200)
        # Should return all products, since filter was ignored
        data = response.json()
        self.assertEqual(len(data["products"]["results"]), 2)
