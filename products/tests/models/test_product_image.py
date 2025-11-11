from django.core.exceptions import ValidationError
from django.test import TestCase

from products.models import ProductImage
from products.factories import (
    ProductFactory,
    ProductVariantFactory,
    ProductImageFactory,
    ProductTypeFactory,
)

class ProductImageValidationTests(TestCase):
    """Unit tests to challenge all validation rules on ProductImage."""

    def setUp(self):
        self.type_with_variants = ProductTypeFactory(has_variants=True)
        self.type_without_variants = ProductTypeFactory(has_variants=False)

        self.product_with_variants = ProductFactory(product_type=self.type_with_variants)
        self.product_without_variants = ProductFactory(product_type=self.type_without_variants)

        self.variant_1 = ProductVariantFactory(product=self.product_with_variants)
        self.variant_2 = ProductVariantFactory(product=self.product_with_variants)

    # ----------------------------------------------------------------------
    # 1. Variant must belong to the same product
    # ----------------------------------------------------------------------

    def test_variant_belongs_to_different_product_raises(self):
        """Should raise if variant belongs to a different product."""
        other_product = ProductFactory(product_type=self.type_with_variants)
        bad_variant = ProductVariantFactory(product=other_product)

        img = ProductImageFactory.build(product=self.product_with_variants, product_variant=bad_variant)

        with self.assertRaises(ValidationError) as ctx:
            img.full_clean()
        self.assertIn("product_variant", ctx.exception.message_dict)

    # ----------------------------------------------------------------------
    # 2. Unique primary image
    # ----------------------------------------------------------------------

    def test_only_one_primary_image_per_product(self):
        """Should raise if adding a second primary image for same product (no variant)."""
        old = ProductImageFactory(product=self.product_with_variants, is_primary=True)
        ProductImageFactory(product=self.product_with_variants, is_primary=True)
        old.refresh_from_db()
        self.assertEqual(old.is_primary, False)

    def test_only_one_primary_image_per_variant(self):
        """Should raise if adding a second primary image for same variant."""
        old = ProductImageFactory(product=self.product_with_variants, product_variant=self.variant_1, is_primary=True)
        ProductImageFactory(product=self.product_with_variants, product_variant=self.variant_1, is_primary=True)
        old.refresh_from_db()
        self.assertEqual(old.is_primary, False)

    # ----------------------------------------------------------------------
    # 4. Unique position per product/variant
    # ----------------------------------------------------------------------

    def test_unique_position_for_product_level_images(self):
        """Should raise if two product-level images share the same position."""
        ProductImageFactory(product=self.product_with_variants, position=0)
        dup = ProductImageFactory.build(product=self.product_with_variants, position=0)

        with self.assertRaises(ValidationError) as ctx:
            dup.full_clean()
        self.assertIn("position", ctx.exception.message_dict)

    def test_unique_position_for_variant_level_images(self):
        """Should raise if two variant images share same position on same variant."""
        ProductImageFactory(product=self.product_with_variants, product_variant=self.variant_1, position=1)
        dup = ProductImageFactory.build(product=self.product_with_variants, product_variant=self.variant_1, position=1)

        with self.assertRaises(ValidationError) as ctx:
            dup.full_clean()
        self.assertIn("position", ctx.exception.message_dict)

    def test_same_position_allowed_on_different_variants(self):
        """Should NOT raise when same position used for different variants."""
        ProductImageFactory(product=self.product_with_variants, product_variant=self.variant_1, position=2)
        img = ProductImageFactory.build(product=self.product_with_variants, product_variant=self.variant_2, position=2)
        # Should pass validation
        img.full_clean()

    # ----------------------------------------------------------------------
    # 5. Miscellaneous
    # ----------------------------------------------------------------------

    def test_valid_image_creation(self):
        """Should pass validation for correct image setup."""
        img = ProductImageFactory.build(product=self.product_with_variants, product_variant=self.variant_1)
        img.full_clean()  # should not raise
