from django.core.exceptions import ValidationError
from django.test import TestCase

from products.factories import (
    ProductFactory,
    ProductVariantFactory,
    ProductStockFactory,
    ProductTypeFactory,
)


class ProductStockTest(TestCase):

    def setUp(self):
        multi_variant_type = ProductTypeFactory(has_variants=True)
        single_variant_type = ProductTypeFactory(has_variants=False)
        self.multi_variant_product = ProductFactory(product_type=multi_variant_type)
        self.single_variant_product = ProductFactory(product_type=single_variant_type)
        self.variant = ProductVariantFactory(product=self.multi_variant_product)

    def test_variant_belongs_to_same_product(self):
        other_product = ProductFactory()
        stock = ProductStockFactory.build(product=other_product, product_variant=self.variant)
        with self.assertRaises(ValidationError) as ctx:
            stock.full_clean()
        self.assertIn("Variant must belong to the product", str(ctx.exception.message_dict))

    def test_reserved_cannot_exceed_quantity(self):
        stock = ProductStockFactory.build(quantity=5, reserved=10)
        with self.assertRaises(ValidationError) as ctx:
            stock.full_clean()
        self.assertIn("Reserved quantity cannot exceed total quantity", str(ctx.exception.message_dict))

    def test_variant_required_for_multi_variant_product(self):
        stock = ProductStockFactory.build(product=self.multi_variant_product, product_variant=None)

        with self.assertRaises(ValidationError) as ctx:
            stock.full_clean()
        self.assertIn(
            "Stock entry for multi-variant product must specify a variant.",
            str(ctx.exception.message_dict)
        )

    def test_unique_constraint_product_and_variant(self):
        stock1 = ProductStockFactory()
        # Duplicate product + variant (None) combination
        stock2 = ProductStockFactory.build(product=stock1.product, product_variant=None)
        with self.assertRaises(ValidationError) as ctx:
            stock2.full_clean()

    def test_available_property_computes_correctly(self):
        stock = ProductStockFactory(quantity=20, reserved=5)
        self.assertEqual(stock.available, 15)

    def test_reserve_decrease_and_release_methods(self):
        stock = ProductStockFactory(quantity=10, reserved=0)

        # Reserve
        stock.reserve(3)
        stock.refresh_from_db()
        self.assertEqual(stock.reserved, 3)

        # Release
        stock.release(2)
        stock.refresh_from_db()
        self.assertEqual(stock.reserved, 1)

        # Decrease
        stock.decrease(4)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 6)
        self.assertEqual(stock.reserved, 0)

        # Increase
        stock.increase(10)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 16)

    def test_reserve_cannot_exceed_available(self):
        stock = ProductStockFactory(quantity=5, reserved=2)
        with self.assertRaises(ValidationError):
            stock.reserve(10)

    def test_unique_stock_per_product_and_variant_validator(self):
        """Ensure stock entry for a product/variant combination is unique."""
        # Case 1: single-variant product (no variant)
        stock1 = ProductStockFactory(product=self.single_variant_product, product_variant=None)

        # Creating another stock for same product with no variant should fail
        duplicate = ProductStockFactory.build(product=self.single_variant_product, product_variant=None)
        with self.assertRaises(ValidationError) as ctx:
            duplicate.full_clean()
        self.assertIn("Stock entry for product/variant already exists.", str(ctx.exception.message_dict))

        # Case 2: same variant
        stock2 = ProductStockFactory(product=self.multi_variant_product, product_variant=self.variant)
        duplicate_variant = ProductStockFactory.build(product=self.multi_variant_product, product_variant=self.variant)
        with self.assertRaises(ValidationError) as ctx:
            duplicate_variant.full_clean()
        self.assertIn("Stock entry for product/variant already exists.", str(ctx.exception.message_dict))

        # Case 3: different variants → valid
        other_variant = ProductVariantFactory(product=self.multi_variant_product)
        stock3 = ProductStockFactory.build(product=self.multi_variant_product, product_variant=other_variant)
        stock3.full_clean()  # should pass, no ValidationError

        # Case 4: product without variant and product with variant → distinct
        product_with_and_without_variant = ProductFactory(product_type=self.multi_variant_product.product_type)
        variant_for_same_product = ProductVariantFactory(product=product_with_and_without_variant)

        ProductStockFactory(product=product_with_and_without_variant, product_variant=None)
        stock_variant = ProductStockFactory.build(product=product_with_and_without_variant, product_variant=variant_for_same_product)
        stock_variant.full_clean()  # should pass, no ValidationError

        # Case 5: updating existing stock (should not raise)
        stock2.quantity = 99
        stock2.full_clean()  # should not raise
