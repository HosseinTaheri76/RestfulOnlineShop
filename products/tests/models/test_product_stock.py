from django.core.exceptions import ValidationError
from django.test import TestCase

from products.factories import (
    ProductFactory,
    ProductSKUFactory,
    ProductStockFactory,
    ProductTypeFactory, ProductCategoryFactory,
)


class ProductStockTest(TestCase):

    @staticmethod
    def build_product_stock(**kwargs):

        has_variant = kwargs.pop("has_variant", False)
        commit = kwargs.pop("commit", True)
        quantity = kwargs.pop("quantity", 100)
        reserved = kwargs.pop("reserved", 0)
        product_type = ProductTypeFactory(has_variants=has_variant)
        product_category = product_type.product_category
        product = kwargs.pop("product", ProductFactory(product_type=product_type, product_category=product_category))
        product_sku = kwargs.pop("product_sku", ProductSKUFactory(product=product))
        if commit:
            return ProductStockFactory(
                product_sku=product_sku,
                quantity=quantity,
                reserved=reserved
            )
        return ProductStockFactory.build(
            product_sku=product_sku,
            quantity=quantity,
            reserved=reserved
        )

    def setUp(self):
        multi_variant_type = ProductTypeFactory(has_variants=True)
        single_variant_type = ProductTypeFactory(has_variants=False)
        self.multi_variant_product = ProductFactory(
            product_type=multi_variant_type,
            product_category=multi_variant_type.product_category
        )
        self.single_variant_product = ProductFactory(
            product_type=single_variant_type,
            product_category=single_variant_type.product_category
        )


    def test_reserved_cannot_exceed_quantity(self):
        stock = self.build_product_stock(quantity=5, reserved=10, commit=False)
        with self.assertRaises(ValidationError) as ctx:
            stock.full_clean()
        self.assertIn("Reserved quantity cannot exceed total quantity", str(ctx.exception.message_dict))


    def test_available_property_computes_correctly(self):
        stock = self.build_product_stock(quantity=20, reserved=5)
        self.assertEqual(stock.available, 15)

    def test_reserve_decrease_and_release_methods(self):
        stock = self.build_product_stock(quantity=10, reserved=0)
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
        stock = self.build_product_stock(quantity=5, reserved=2)
        with self.assertRaises(ValidationError):
            stock.reserve(10)

    def test_unique_stock_per_product_and_variant_validator(self):
        """Ensure stock entry for a product/variant combination is unique."""
        # Case 1: single-variant product (no variant)
        stock = self.build_product_stock(commit=True)

        duplicate_stock = self.build_product_stock(product_sku=stock.product_sku, commit=False)

        with self.assertRaises(ValidationError) as ctx:
            duplicate_stock.full_clean()

        self.assertIn('Stock entry for this SKU already exists.', str(ctx.exception.message_dict))

