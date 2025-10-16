from unicodedata import category

from django.test import TestCase
from django.core.exceptions import ValidationError

from products import factories
from products.models import ProductType


class ProductTypeModelTests(TestCase):
    """Tests for ProductType model validation and behavior."""

    def setUp(self):
        self.type_with_variants = factories.ProductTypeFactory(has_variants=True)
        self.type_without_variants = factories.ProductTypeFactory(has_variants=False)
        self.in_active_category = factories.ProductCategoryFactory(is_active=False)

    # --- VALID CASES ---

    def test_can_create_product_type_with_or_without_variants(self):
        """Creating product types with or without variants should be valid."""
        self.type_with_variants.full_clean()
        self.type_without_variants.full_clean()
        self.assertTrue(ProductType.objects.exists())

    def test_can_change_has_variants_if_no_products_exist(self):
        """It should allow changing has_variants when there are no linked products."""
        product_type = factories.ProductTypeFactory(has_variants=True)
        product_type.has_variants = False
        product_type.full_clean()  # Should not raise
        product_type.save()
        self.assertFalse(product_type.has_variants)

    # --- INVALID CASES ---

    def test_cannot_change_has_variants_when_products_exist(self):
        """
        Should raise ValidationError when attempting to toggle has_variants
        for a product type that already has products.
        """
        product_type = factories.ProductTypeFactory(has_variants=True)
        factories.ProductFactory(product_type=product_type)

        product_type.has_variants = False  # toggle the field
        with self.assertRaises(ValidationError) as ctx:
            product_type.full_clean()

        self.assertIn("has_variants", ctx.exception.message_dict)
        self.assertIn("Cannot change this field", ctx.exception.message_dict["has_variants"][0])

    def test_validation_works_in_both_directions(self):
        """
        Should block both enabling and disabling variant support once products exist.
        """
        type_with_variants = factories.ProductTypeFactory(has_variants=True)
        type_without_variants = factories.ProductTypeFactory(has_variants=False)

        # Add product to each
        factories.ProductFactory(product_type=type_with_variants)
        factories.ProductFactory(product_type=type_without_variants)

        # Try to toggle each direction
        type_with_variants.has_variants = False
        type_without_variants.has_variants = True

        for product_type in (type_with_variants, type_without_variants):
            with self.assertRaises(ValidationError):
                product_type.full_clean()

    # --- OTHER TESTS ---

    def test_str_representation(self):
        """Ensure ProductType string representation is user-friendly."""
        product_type = factories.ProductTypeFactory(title="Smartphones")
        self.assertEqual(str(product_type), "Smartphones")


    def test_cannot_activate_product_under_inactive_category(self):
        product = factories.ProductFactory(product_category=self.in_active_category, is_active=False)
        product.is_active = True

        with self.assertRaises(ValidationError) as ctx:
            product.full_clean()

        self.assertIn("Cannot activate product", str(ctx.exception))