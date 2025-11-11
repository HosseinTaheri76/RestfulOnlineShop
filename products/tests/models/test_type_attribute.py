from django.test import TestCase
from django.core.exceptions import ValidationError

from products import factories
from products.models import ProductAttribute, ProductTypeAttribute


class ProductTypeAttributeModelTests(TestCase):
    """Unit tests for the ProductTypeAttribute model validation and behavior."""

    def setUp(self):
        """Prepare reusable product types and attributes for test cases."""
        self.product_type_with_variants = factories.ProductTypeFactory(has_variants=True)
        self.product_type_without_variants = factories.ProductTypeFactory(has_variants=False)
        self.product_attribute = factories.ProductAttributeFactory(scope=ProductAttribute.Scope.PRODUCT)
        self.variant_attribute = factories.ProductAttributeFactory(scope=ProductAttribute.Scope.VARIANT)

    # --- Helpers ---

    @staticmethod
    def _create_type_attribute(product_type, attribute, **kwargs):
        """Helper for creating and validating a ProductTypeAttribute instance."""
        type_attribute = ProductTypeAttribute(
            product_type=product_type,
            product_attribute=attribute,
            **kwargs,
        )
        type_attribute.full_clean()
        type_attribute.save()
        return type_attribute

    # --- VALID CASES ---

    def test_variant_attribute_allowed_for_type_with_variants(self):
        """Variant-level attributes should be valid when the product type supports variants."""
        type_attribute = self._create_type_attribute(self.product_type_with_variants, self.variant_attribute)
        self.assertTrue(type_attribute.pk)
        self.assertEqual(type_attribute.product_type, self.product_type_with_variants)
        self.assertEqual(type_attribute.product_attribute, self.variant_attribute)

    def test_product_attribute_allowed_for_all_types(self):
        """Product-level attributes should be valid for both variant and non-variant types."""
        # Product type without variants
        type_attribute_1 = self._create_type_attribute(self.product_type_without_variants, self.product_attribute)
        # Product type with variants
        type_attribute_2 = self._create_type_attribute(self.product_type_with_variants, self.product_attribute)
        self.assertNotEqual(type_attribute_1.pk, type_attribute_2.pk)
        self.assertEqual(type_attribute_1.product_attribute.scope, ProductAttribute.Scope.PRODUCT)

    # --- INVALID CASES ---

    def test_variant_attribute_not_allowed_for_nonvariant_type(self):
        """Should raise ValidationError if a non-variant type gets a variant attribute."""
        type_attribute = ProductTypeAttribute(
            product_type=self.product_type_without_variants,
            product_attribute=self.variant_attribute,
        )

        with self.assertRaises(ValidationError) as context:
            type_attribute.full_clean()

        self.assertIn(
            "does not support variant-level attributes",
            str(context.exception),
        )

    def test_duplicate_type_attribute_combination_not_allowed(self):
        """Should not allow the same (type, attribute) pair to be assigned twice."""
        self._create_type_attribute(self.product_type_with_variants, self.product_attribute)

        duplicate_type_attribute = ProductTypeAttribute(
            product_type=self.product_type_with_variants,
            product_attribute=self.product_attribute,
        )

        with self.assertRaises(ValidationError) as context:
            duplicate_type_attribute.full_clean()

    # --- OTHER TESTS ---

    def test_str_representation(self):
        """Ensure the __str__ method produces a readable representation."""
        type_attribute = self._create_type_attribute(self.product_type_with_variants, self.variant_attribute)
        expected = f"{self.product_type_with_variants.title} → {self.variant_attribute.title}"
        self.assertEqual(str(type_attribute), expected)


    # def test_cannot_change_type_attribute_referenced_by_SkuAttributeOption(self):
    #     todo: fix this test
    #     ta = factories.ProductTypeAttributeFactory(
    #         product_type=self.product_type_without_variants,
    #         product_attribute=self.product_attribute,
    #     )
    #
    #     product = factories.ProductFactory(
    #         product_type=self.product_type_without_variants,
    #         product_category=self.product_type_without_variants.product_category,
    #     )
    #
    #     factories.ProductSKUAttributeValueFactory(
    #         product=product,
    #         product_type_attribute=ta,
    #         value=factories.ProductAttributeOptionFactory(product_attribute=self.product_attribute)
    #     )
    #
    #     ta.product_type = factories.ProductTypeFactory(has_variants=False)
    #
    #     with self.assertRaises(ValidationError) as ctx:
    #         ta.clean()
    #
    #     self.assertIn(
    #         "Cannot modify a ProductTypeAttribute that is in use by products",
    #         str(ctx.exception),
    #     )
