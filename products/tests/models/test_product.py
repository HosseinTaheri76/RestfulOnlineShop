from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase

from products import models
from products.factories import (
    ProductFactory,
    ProductTypeFactory,
    ProductCategoryFactory,
    ProductAttributeFactory,
    ProductSKUFactory,
    ProductTypeAttributeFactory
)


class ProductModelValidationTests(TestCase):
    """Test validations and logical consistency of the Product model."""

    def setUp(self):
        self.category = ProductCategoryFactory()
        self.type_with_variants = ProductTypeFactory(has_variants=True)
        self.type_without_variants = ProductTypeFactory(has_variants=False)
        self.product_attr_required = ProductAttributeFactory.create(
            scope=models.ProductAttribute.Scope.PRODUCT,
            title="CPU",
        )
        self.variant_attr_required = ProductAttributeFactory.create(
            scope=models.ProductAttribute.Scope.SKU,
            title="Storage",
        )
        ProductTypeAttributeFactory.create(
            product_type=self.type_with_variants,
            product_attribute=self.product_attr_required,
            required=True,
        )
        ProductTypeAttributeFactory.create(
            product_type=self.type_with_variants,
            product_attribute=self.variant_attr_required,
            required=True,
        )
        self.product = ProductFactory.create(product_type=self.type_with_variants)


    def test_active_manager_returns_only_products_and_categories_that_are_active(self):
        """ActiveProductManager should only return products and categories that are active."""
        # active category + active product → should appear
        active_category = ProductCategoryFactory(is_active=True)
        product_type = ProductTypeFactory(product_category=active_category, has_variants=False)
        active_product = ProductFactory(
            product_category=active_category,
            is_active=True,
            product_type=product_type,
        )

        active_products = models.Product.active.all()

        # Assert
        self.assertIn(active_product, active_products)

        # inactive product → should not appear
        inactive_product = ProductFactory(
            product_category=active_category,
            is_active=False,
            product_type=product_type,
        )
        active_products = models.Product.active.all()
        self.assertNotIn(inactive_product, active_products)

        # inactive category → should not appear
        inactive_category_product = ProductFactory(
            product_category=active_category,
            is_active=True,
            product_type=product_type,
        )
        active_category.is_active = False
        active_category.save()
        # Act
        active_products = models.Product.active.all()
        self.assertNotIn(inactive_product, active_products)
        self.assertNotIn(inactive_category_product, active_products)

    def test_slug_is_generated_from_title(self):
        """Ensure slug auto-generates correctly from title."""
        product = ProductFactory(
            title="Test Product Slug",
            slug=None,
            product_type=self.type_with_variants,
            product_category=self.type_with_variants.product_category,
        )
        product.full_clean()
        product.save()
        self.assertEqual(product.slug, "test-product-slug")

    def test_create_required_product_attributes(self):
        """Ensure required PRODUCT-scope attributes are created after product save."""
        self.product._create_required_attributes()

        attrs = models.ProductSKUAttributeValue.objects.filter(
            product=self.product, product_sku__isnull=True
        )
        self.assertEqual(attrs.count(), 1)
        self.assertEqual(
            attrs.first().product_type_attribute.product_attribute, self.product_attr_required
        )

    def test_does_not_duplicate_existing_attributes(self):
        """Ensure required attributes are not created twice."""
        # Call once
        self.product._create_required_attributes()
        count_first = models.ProductSKUAttributeValue.objects.count()

        # Call again
        self.product._create_required_attributes()
        count_second = models.ProductSKUAttributeValue.objects.count()

        self.assertEqual(count_first, count_second)

    def test_product_variant_primary_handling(self):
        """Ensure the first variant becomes primary automatically."""

        variant1 = ProductSKUFactory.create(product=self.product)
        self.assertTrue(variant1.is_primary)

        variant2 = ProductSKUFactory.create(product=self.product, is_primary=True)
        variant1.refresh_from_db()
        variant2.refresh_from_db()

        self.assertFalse(variant1.is_primary)
        self.assertTrue(variant2.is_primary)