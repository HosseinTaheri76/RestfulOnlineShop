from django.test import TestCase
from django.core.exceptions import ValidationError

from products import factories
from products.models import ProductVariant


class ProductVariantModelTests(TestCase):
    """Tests for ProductVariant model validation and behavior."""

    def setUp(self):
        """Create reusable objects for tests."""
        self.type_with_variants = factories.ProductTypeFactory(has_variants=True)
        self.type_without_variants = factories.ProductTypeFactory(has_variants=False)
        self.category = factories.ProductCategoryFactory(is_root=True)

        # Products
        self.product_with_variants = factories.ProductFactory(product_type=self.type_with_variants)
        self.product_without_variants = factories.ProductFactory(product_type=self.type_without_variants)

    # --- VALID CASES ---

    def test_valid_variant_for_product_with_variants(self):
        """A variant should be valid when the product type supports variants."""
        variant = factories.ProductVariantFactory.build(
            product=self.product_with_variants,
            sku="SKU123",
            title="Blue Variant",
            is_active=True,
        )
        variant.full_clean()  # should not raise
        variant.save()
        self.assertIsNotNone(variant.pk)
        self.assertEqual(str(variant), "Blue Variant")

    def test_variant_title_falls_back_to_product_name(self):
        """If no title is given, __str__ should use product title."""
        variant = factories.ProductVariantFactory(
            product=self.product_with_variants,
            sku="SKU999",
        )
        self.assertIn(self.product_with_variants.title, str(variant))

    # --- INVALID CASES ---

    def test_variant_not_allowed_for_product_without_variants(self):
        """Should raise ValidationError if product type does not support variants."""
        variant = factories.ProductVariantFactory(
            product=self.product_without_variants,
            sku="SKU124",
            title="Invalid Variant",
        )

        with self.assertRaises(ValidationError) as ctx:
            variant.full_clean()

        self.assertIn("cannot have variants", str(ctx.exception))


    # --- ACTIVE STATUS TESTS ---

    def test_inactive_category_or_product_disables_variant_in_active_manager(self):
        """
        Ensure that inactive products or categories make variants
        invisible to ActiveProductVariantManager (if implemented).
        """
        variant = factories.ProductVariantFactory(
            product=self.product_with_variants,
            sku="SKU-ACTIVE",
        )
        # Initially active
        self.assertTrue(variant.is_active)
        self.assertIn(variant, ProductVariant.active.all())

        # Deactivate product or category should exclude it
        self.product_with_variants.is_active = False
        self.product_with_variants.save()
        self.assertNotIn(variant, ProductVariant.active.all())

        # Re-activate product, deactivate category
        self.product_with_variants.is_active = True
        self.product_with_variants.save()
        self.product_with_variants.product_category.is_active = False
        self.product_with_variants.product_category.save()
        self.assertNotIn(variant, ProductVariant.active.all())

    # --- OTHER TESTS ---

    def test_str_representation_with_title(self):
        """Ensure string representation prefers variant title."""
        variant = factories.ProductVariantFactory(
            product=self.product_with_variants,
            sku="SKU-TITLE",
            title="Red Model",
        )
        self.assertEqual(str(variant), "Red Model")

    def test_cannot_activate_variant_under_inactive_product(self):
        self.product_with_variants.is_active = False
        self.product_with_variants.save()
        variant = factories.ProductVariantFactory(
            is_active=False,
            product=self.product_with_variants,
        )
        variant.is_active = True
        with self.assertRaises(ValidationError) as ctx:
            variant.full_clean()

        self.assertIn("Cannot activate variant", str(ctx.exception))