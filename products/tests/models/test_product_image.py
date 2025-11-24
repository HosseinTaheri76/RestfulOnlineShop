from django.core.exceptions import ValidationError
from django.test import TestCase

from products.models import ProductImage
from products.factories import (
    ProductFactory,
    ProductSKUFactory,
    ProductImageFactory,
    ProductTypeFactory,
)

class ProductImageValidationTests(TestCase):
    """Unit tests to challenge all validation rules on ProductImage."""

    def setUp(self):
        self.sku_1 = ProductSKUFactory()
        self.sku_2 = ProductSKUFactory()

    def test_only_one_primary_image_per_sku(self):
        """Should raise if adding a second primary image for same product (no variant)."""
        old = ProductImageFactory(product_sku=self.sku_1, is_primary=True)
        ProductImageFactory(product_sku=self.sku_1, is_primary=True)
        old.refresh_from_db()
        self.assertEqual(old.is_primary, False)

    # ----------------------------------------------------------------------
    # 4. Unique position per product/variant
    # ----------------------------------------------------------------------

    def test_unique_position_for_product_level_images(self):
        """Should raise if two product-level images share the same position."""
        ProductImageFactory(product_sku=self.sku_1, position=0)
        dup = ProductImageFactory.build(product_sku=self.sku_1, position=0)

        with self.assertRaises(ValidationError) as ctx:
            dup.full_clean()
        self.assertIn("position", ctx.exception.message_dict)



    # ----------------------------------------------------------------------
    # 5. Miscellaneous
    # ----------------------------------------------------------------------

    def test_valid_image_creation(self):
        """Should pass validation for correct image setup."""
        img = ProductImageFactory.build(product_sku=self.sku_1)
        img.full_clean()  # should not raise
