from django.test import TestCase
from django.core.exceptions import ValidationError

from products.factories import (
    ProductFactory,
    ProductTypeFactory,
    ProductSKUFactory,
    ProductAttributeFactory,
    ProductTypeAttributeFactory,
)
from products.models import ProductSKU, ProductSKUAttributeValue


class ProductSKUTest(TestCase):

    # Single-SKU products
    def test_single_sku_product_cannot_have_multiple_skus(self):
        pt = ProductTypeFactory(has_variants=False)
        p = ProductFactory(product_type=pt)

        ProductSKUFactory(product=p, is_primary=True)

        with self.assertRaises(ValidationError):
            sku = ProductSKUFactory.build(product=p)
            sku.full_clean()
            sku.save()

    def test_single_sku_product_primary_is_auto_set(self):
        pt = ProductTypeFactory(has_variants=False)
        p = ProductFactory(product_type=pt)

        sku = ProductSKUFactory.build(product=p, is_primary=False)
        sku.full_clean()
        sku.save()

        self.assertTrue(sku.is_primary)

    # Multi-SKU products
    def test_multi_sku_product_can_have_multiple_skus(self):
        pt = ProductTypeFactory(has_variants=True)
        p = ProductFactory(product_type=pt)

        s1 = ProductSKUFactory(product=p)
        s2 = ProductSKUFactory(product=p)

        self.assertEqual(p.skus.count(), 2)

    # Primary SKU rules
    def test_setting_primary_unsets_other_primary(self):
        pt = ProductTypeFactory(has_variants=True)
        p = ProductFactory(product_type=pt)

        a = ProductSKUFactory(product=p, is_primary=True)
        b = ProductSKUFactory(product=p, is_primary=False)

        b.is_primary = True
        b.full_clean()
        b.save()

        a.refresh_from_db()
        b.refresh_from_db()

        self.assertFalse(a.is_primary)
        self.assertTrue(b.is_primary)

    def test_product_must_always_have_one_primary_sku(self):
        pt = ProductTypeFactory(has_variants=True)
        p = ProductFactory(product_type=pt)

        sku = ProductSKUFactory(product=p, is_primary=True)

        sku.is_primary = False
        sku.full_clean()
        sku.save()

        sku.refresh_from_db()
        self.assertTrue(sku.is_primary)

    # Primary deactivation
    def test_cannot_deactivate_primary_sku_of_active_product(self):
        pt = ProductTypeFactory(has_variants=True)
        p = ProductFactory(product_type=pt, is_active=True)

        sku = ProductSKUFactory(product=p, is_primary=True)
        sku.is_active = False

        with self.assertRaises(ValidationError):
            sku.full_clean()

    # Unique title per product
    def test_title_unique_per_product(self):
        pt = ProductTypeFactory(has_variants=True)
        p = ProductFactory(product_type=pt)

        ProductSKUFactory(product=p, title="Blue")

        duplicate = ProductSKUFactory.build(product=p, title="Blue")

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    # Required SKU attributes auto-created
    def test_required_sku_attributes_are_auto_created(self):
        pt = ProductTypeFactory(has_variants=True)

        attr = ProductAttributeFactory(scope="sku")

        tattr = ProductTypeAttributeFactory(
            product_type=pt,
            product_attribute=attr,
            required=True,
        )

        p = ProductFactory(product_type=pt)
        sku = ProductSKUFactory(product=p)

        created = ProductSKUAttributeValue.objects.filter(product_sku=sku)

        self.assertEqual(created.count(), 1)
        self.assertEqual(created.first().product_type_attribute_id, tattr.id)

    # SKU being moved between products
    def test_switching_sku_to_another_product_updates_primary_rules(self):
        pt = ProductTypeFactory(has_variants=True)

        p1 = ProductFactory(product_type=pt)
        p2 = ProductFactory(product_type=pt)

        a = ProductSKUFactory(product=p1, is_primary=True)
        b = ProductSKUFactory(product=p2, is_primary=True)

        a.product = p2
        a.full_clean()
        a.save()

        a.refresh_from_db()
        b.refresh_from_db()

        self.assertTrue(a.is_primary)
        self.assertFalse(b.is_primary)
