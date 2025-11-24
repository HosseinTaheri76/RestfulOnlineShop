from django.core.exceptions import ValidationError
from django.test import TestCase

from products import models
from products.models import ProductSKUAttributeValue
from products.factories import (
    ProductFactory,
    ProductTypeFactory,
    ProductSKUFactory,
    ProductAttributeFactory,
    ProductTypeAttributeFactory,
    ProductAttributeOptionFactory,
    ProductSKUAttributeValueFactory,
)


class TestProductSKUAttributeValue(TestCase):


    def test_valid_product_attribute_value_creation(self):
        """Valid instance should pass validation and save successfully."""
        value = ProductSKUAttributeValueFactory()
        value.full_clean()  # should not raise
        value.save()
        self.assertIsNotNone(value.pk)
        self.assertEqual(value.product_type_attribute.product_type, value.product.product_type)

    def test_variant_must_belong_to_product(self):
        """Ensure variant must belong to the same product."""
        product_type = ProductTypeFactory(has_variants=True)
        product = ProductFactory(product_type=product_type)
        variant = ProductSKUFactory(product=product)
        other_product = ProductFactory(product_type=product_type)
        attribute = ProductAttributeFactory(
            scope=models.ProductAttribute.Scope.SKU
        )
        ta = ProductTypeAttributeFactory(
            product_type=other_product.product_type,
            product_attribute=attribute,
        )
        attr_value = ProductAttributeOptionFactory(
            product_attribute=attribute,
        )
        value = ProductSKUAttributeValueFactory.build(
            product=other_product,
            product_sku=variant,
            product_type_attribute=ta,
            value=attr_value,
        )

        with self.assertRaises(ValidationError) as ctx:
            value.full_clean()

        self.assertIn("product_sku", ctx.exception.message_dict)

    def test_attribute_must_belong_to_product_type(self):
        """Ensure attribute belongs to the product's type."""
        p = ProductFactory()
        wrong_type_attr = ProductTypeAttributeFactory()  # unrelated type

        value = ProductSKUAttributeValueFactory.build(
            product=p,
            product_type_attribute=wrong_type_attr,
        )

        with self.assertRaises(ValidationError) as ctx:
            value.full_clean()

        self.assertIn("product_type_attribute", ctx.exception.message_dict)

    def test_attribute_option_must_belong_to_attribute(self):
        """Ensure selected option belongs to the correct attribute."""
        pt = ProductTypeFactory(has_variants=False)
        p = ProductFactory(product_type=pt)
        attribute = ProductAttributeFactory(scope=models.ProductAttribute.Scope.PRODUCT)
        type_attr = ProductTypeAttributeFactory(product_type=p.product_type, product_attribute=attribute)
        wrong_option = ProductAttributeOptionFactory()  # belongs to a different attribute

        value = ProductSKUAttributeValueFactory.build(
            product=p,
            product_type_attribute=type_attr,
            value=wrong_option,
        )

        with self.assertRaises(ValidationError) as ctx:
            value.full_clean()

        self.assertIn("value", ctx.exception.message_dict)

    def test_variant_scope_mismatch_validation(self):
        """Ensure product-wide attributes cannot be assigned to a variant."""
        pt = ProductTypeFactory(has_variants=True)
        p = ProductFactory(product_type=pt)
        variant = ProductSKUFactory(product=p)
        attr = ProductAttributeFactory(scope="product")
        type_attr = ProductTypeAttributeFactory(
            product_type=p.product_type,
            product_attribute=attr,
        )
        opt = ProductAttributeOptionFactory(product_attribute=attr)

        value = ProductSKUAttributeValueFactory.build(
            product=p,
            product_sku=variant,
            product_type_attribute=type_attr,
            value=opt,
        )

        with self.assertRaises(ValidationError) as ctx:
            value.full_clean()

        self.assertIn("cannot be assigned to SKUs.", str(ctx.exception.message_dict))

    # def test_unique_constraint_product_variant_and_attribute(self):
    #     Todo: fix this test
    #     """Ensure combination of product, variant, and attribute is unique."""
    #     value1 = ProductSKUAttributeValueFactory(product_variant=ProductVariantFactory(
    #         product=ProductFactory()
    #     ))
    #     value2 = ProductSKUAttributeValueFactory.build(
    #         product=value1.product,
    #         product_variant=value1.product_variant,
    #         product_type_attribute=value1.product_type_attribute,
    #         value=value1.value,
    #     )
    #
    #     # `save()` should raise IntegrityError due to unique constraint
    #     from django.db.utils import IntegrityError
    #     with self.assertRaises(IntegrityError):
    #         value2.save()
