from django.test import TestCase
from django.core.exceptions import ValidationError

from products import factories, models
from products.models import ProductVariant, ProductAttribute


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

        self.variant_attr_required = factories.ProductAttributeFactory.create(
            scope=ProductAttribute.Scope.VARIANT,
            title="Color",
        )

        factories.ProductTypeAttributeFactory.create(
            product_type=self.type_with_variants,
            product_attribute=self.variant_attr_required,
            required=True,
        )


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
        self.assertIn("Blue Variant", str(variant))

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
        self.assertIn("Red Model", str(variant))

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

    # ────────────────────────────────
    # PRIMARY HANDLING LOGIC TESTS
    # ────────────────────────────────

    def test_saving_primary_variant_unsets_other_primaries(self):
        """When a new variant is saved as primary, it demotes previous primaries."""
        v1 = factories.ProductVariantFactory(product=self.product_with_variants, is_primary=True)
        v2 = factories.ProductVariantFactory(product=self.product_with_variants, is_primary=False)

        # Make v2 primary
        v2.is_primary = True
        v2.save()
        v1.refresh_from_db()
        v2.refresh_from_db()

        self.assertTrue(v2.is_primary)
        self.assertFalse(v1.is_primary)

    def test_first_variant_becomes_primary_automatically(self):
        """If no primary exists, first variant saved becomes primary automatically."""
        v1 = factories.ProductVariantFactory(product=self.product_with_variants, is_primary=False)
        self.assertTrue(v1.is_primary)

    def test_non_primary_variant_does_not_affect_existing_primary(self):
        """Saving a non-primary variant should not unset existing primaries."""
        v1 = factories.ProductVariantFactory(product=self.product_with_variants, is_primary=True)
        v2 = factories.ProductVariantFactory(product=self.product_with_variants, is_primary=False)
        v2.is_primary = False
        v2.save()

        v1.refresh_from_db()
        v2.refresh_from_db()

        self.assertTrue(v1.is_primary)
        self.assertFalse(v2.is_primary)


    def test_create_required_variant_attributes(self):
        """Ensure required VARIANT-scope attributes are created after variant save."""
        variant = factories.ProductVariantFactory.create(product=self.product_with_variants)

        variant._create_required_attributes()

        attrs = models.ProductSKUAttributeValue.objects.filter(product_variant=variant)
        self.assertEqual(attrs.count(), 1)
        self.assertEqual(
            attrs.first().product_type_attribute.product_attribute, self.variant_attr_required
        )

    def test_does_not_duplicate_existing_variant_attributes(self):
        """Ensure required VARIANT attributes are not duplicated."""
        variant = factories.ProductVariantFactory.create(product=self.product_with_variants)
        variant._create_required_attributes()
        first_count = models.ProductSKUAttributeValue.objects.count()

        variant._create_required_attributes()
        second_count = models.ProductSKUAttributeValue.objects.count()

        self.assertEqual(first_count, second_count)