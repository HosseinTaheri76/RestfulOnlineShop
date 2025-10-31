from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase

from products import models
from products.factories import (
    ProductFactory,
    ProductTypeFactory,
    ProductCategoryFactory,
    ProductAttributeFactory,
    ProductVariantFactory,
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
            scope=models.ProductAttribute.Scope.VARIANT,
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

    def test_product_with_variants_must_not_have_price(self):
        """A product with variants should not have a price value."""
        product = ProductFactory(
            product_type=self.type_with_variants,
            product_category=self.category,
            price=Decimal("99.99")
        )

        with self.assertRaises(ValidationError) as ctx:
            product.full_clean()
        self.assertIn("price", ctx.exception.message_dict)
        self.assertIn("must be empty", ctx.exception.message_dict["price"][0])

    def test_product_without_variants_must_have_price(self):
        """A product without variants must define a price."""
        product = ProductFactory(
            product_type=self.type_without_variants,
            product_category=self.category,
            price=None
        )

        with self.assertRaises(ValidationError) as ctx:
            product.full_clean()
        self.assertIn("price", ctx.exception.message_dict)
        self.assertIn("must be filled", ctx.exception.message_dict["price"][0])

    def test_product_with_variants_can_have_no_price(self):
        """A product with variants and no price should pass validation."""
        product = ProductFactory(
            product_type=self.type_with_variants,
            product_category=self.type_with_variants.product_category,
            price=None
        )
        try:
            product.full_clean()
        except ValidationError:
            self.fail("Product with variants and no price raised ValidationError unexpectedly.")

    def test_product_without_variants_with_price_is_valid(self):
        """A product without variants and a price should be valid."""
        product = ProductFactory(
            product_type=self.type_without_variants,
            product_category=self.type_without_variants.product_category,
            price=Decimal("49.99"),
            sku='123456'
        )
        try:
            product.full_clean()
        except ValidationError:
            self.fail("Product without variants and price raised ValidationError unexpectedly.")

    def test_active_manager_returns_only_products_and_categories_that_are_active(self):
        """ActiveProductManager should only return products and categories that are active."""
        # active category + active product → should appear
        active_category = ProductCategoryFactory(is_active=True)
        active_product = ProductFactory(
            product_category=active_category,
            is_active=True,
            price=Decimal("10.00"),
            product_type=self.type_without_variants,
        )

        # inactive product → should not appear
        inactive_product = ProductFactory(
            product_category=active_category,
            is_active=False,
            price=Decimal("10.00"),
            product_type=self.type_without_variants,
        )

        # inactive category → should not appear
        inactive_category = ProductCategoryFactory(is_active=False)
        inactive_category_product = ProductFactory(
            product_category=inactive_category,
            is_active=True,
            price=Decimal("10.00"),
            product_type=self.type_without_variants,
        )

        # Act
        active_products = models.Product.active.all()

        # Assert
        self.assertIn(active_product, active_products)
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
            product=self.product, product_variant__isnull=True
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

        variant1 = ProductVariantFactory.create(product=self.product)
        self.assertTrue(variant1.is_primary)

        variant2 = ProductVariantFactory.create(product=self.product, is_primary=True)
        variant1.refresh_from_db()
        variant2.refresh_from_db()

        self.assertFalse(variant1.is_primary)
        self.assertTrue(variant2.is_primary)