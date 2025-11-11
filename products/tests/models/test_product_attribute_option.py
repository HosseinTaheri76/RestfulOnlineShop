from django.core.exceptions import ValidationError
from django.test import TestCase

from products import models
from products import factories


# class TestProductAttributeOption(TestCase):
#
#     def setUp(self):
#         product_type = factories.ProductTypeFactory(has_variants=False)
#         product_attribute = factories.ProductAttributeFactory(scope=models.ProductAttribute.Scope.PRODUCT)
#         type_attribute = factories.ProductTypeAttributeFactory(
#             product_type=product_type,
#             product_attribute=product_attribute
#         )
#         self.unused_attribute_option = factories.ProductAttributeOptionFactory()
#         self.used_attribute_option = factories.ProductAttributeOptionFactory(product_attribute=product_attribute)
#         self.product = factories.ProductFactory(
#             product_category=product_type.product_category,
#             product_type=product_type
#         )
#         self.product.attribute_values.create(
#             value=self.used_attribute_option,
#             product_type_attribute=type_attribute,
#         )
#
#     def test_cannot_change_used_attribute_option(self):
#         self.used_attribute_option.value = 'something new'
#
#         with self.assertRaises(ValidationError) as ctx:
#             self.used_attribute_option.clean()
#
#         self.assertIn("Cannot modify an option that is in use by products", str(ctx.exception))
#
#     def test_can_change_unused_attribute_option(self):
#         self.unused_attribute_option.value = 'something new'
#         self.unused_attribute_option.clean()
# todo: fix this