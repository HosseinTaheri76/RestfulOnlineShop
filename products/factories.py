import factory
from django.core.files.base import ContentFile
from django.utils.text import slugify
from faker import Faker

from . import models

fake = Faker()


# --------------------------------------------------------
# Category Factory
# --------------------------------------------------------
class ProductCategoryFactory(factory.django.DjangoModelFactory):
    """
    Factory for ProductCategory.

    Supports hierarchical category creation using `is_root` and `children` parameters.

    Usage:
        root = ProductCategoryFactory(is_root=True)
        child = ProductCategoryFactory(is_root=False, parent=root)
        root_with_children = ProductCategoryFactory(children=3)
    """

    class Meta:
        model = models.ProductCategory

    class Params:
        is_root = True  # if False, attaches to a root category

    title = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.LazyAttribute(lambda o: slugify(o.title))
    description = factory.Faker("sentence", nb_words=8)
    is_active = True

    @factory.lazy_attribute
    def parent(self):
        # Avoid infinite recursion — only assign a parent if not a root category
        if not self.is_root:
            # Create or reuse a root-level parent
            return ProductCategoryFactory(is_root=True)
        return None

    @factory.post_generation
    def children(self, create, extracted, **kwargs):
        """Optionally generate subcategories after creation."""
        if create and extracted:
            for _ in range(extracted):
                ProductCategoryFactory(parent=self, is_root=False)


# --------------------------------------------------------
# Product Type Factory
# --------------------------------------------------------
class ProductTypeFactory(factory.django.DjangoModelFactory):
    """
    Factory for ProductType.
    """

    class Meta:
        model = models.ProductType

    title = factory.Sequence(lambda n: f"Type {n}")
    has_variants = factory.Faker("boolean")
    product_category = factory.SubFactory(ProductCategoryFactory)

# --------------------------------------------------------
# Product Brand Factory
# --------------------------------------------------------

class ProductBrandFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = models.ProductBrand

    title = factory.Sequence(lambda n: f"Brand {n}")
    slug = factory.LazyAttribute(lambda o: slugify(o.title))


# --------------------------------------------------------
# Product Attribute Factory
# --------------------------------------------------------
class ProductAttributeFactory(factory.django.DjangoModelFactory):
    """
    Factory for ProductAttribute.
    """

    class Meta:
        model = models.ProductAttribute

    title = factory.Sequence(lambda n: f"Attribute {n}")
    scope = factory.Iterator(models.ProductAttribute.Scope.values)
    filterable = factory.Faker("boolean")


# --------------------------------------------------------
# Product Type Attribute Factory
# --------------------------------------------------------
class ProductTypeAttributeFactory(factory.django.DjangoModelFactory):
    """
    Factory for ProductTypeAttribute.
    """

    class Meta:
        model = models.ProductTypeAttribute

    product_type = factory.SubFactory(ProductTypeFactory)
    product_attribute = factory.SubFactory(ProductAttributeFactory)
    required = factory.Faker("boolean")


# --------------------------------------------------------
# Product Factory
# --------------------------------------------------------
class ProductFactory(factory.django.DjangoModelFactory):
    """
    Factory for Product.

    Automatically handles price rules:
        - Adds price only for non-variant product types.
        - Leaves price empty when `has_variants=True`.
    """

    class Meta:
        model = models.Product

    product_type = factory.SubFactory(ProductTypeFactory)
    product_category = factory.SubFactory(ProductCategoryFactory, is_root=False)
    product_brand = factory.SubFactory(ProductBrandFactory)
    title = factory.Sequence(lambda n: f"Product {n}")
    slug = factory.LazyAttribute(lambda o: slugify(o.title))
    description = factory.Faker("paragraph", nb_sentences=2)
    is_active = True

    @factory.lazy_attribute
    def price(self):
        # Assign price only for single-variant products
        return fake.pydecimal(
            left_digits=4,
            right_digits=2,
            positive=True) if not self.product_type.has_variants else None


class ProductVariantFactory(factory.django.DjangoModelFactory):
    """
    Factory for generating ProductVariant instances for testing.

    Automatically creates a related Product (via ProductFactory) unless one is provided.
    """

    class Meta:
        model = models.ProductVariant

    product = factory.SubFactory(ProductFactory)
    price = factory.LazyAttribute(lambda _: round(fake.pydecimal(left_digits=4, right_digits=2, positive=True), 2))
    sku = factory.LazyAttribute(lambda _: fake.unique.bothify(text="SKU-####"))
    title = factory.LazyAttribute(lambda _: fake.word().capitalize())
    is_active = True


class ProductAttributeOptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductAttributeOption

    product_attribute = factory.SubFactory(ProductAttributeFactory)
    value = factory.LazyAttribute(lambda _: fake.word())


class ProductSKUAttributeValueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductSKUAttributeValue

    product = factory.SubFactory(ProductFactory)
    product_variant = None
    product_type_attribute = factory.LazyAttribute(
        lambda o: ProductTypeAttributeFactory(product_type=o.product.product_type)
    )
    value = factory.LazyAttribute(
        lambda o: ProductAttributeOptionFactory(product_attribute=o.product_type_attribute.product_attribute)
    )


class ProductImageFactory(factory.django.DjangoModelFactory):
    """
    Factory for creating ProductImage instances for testing.
    Automatically generates a fake image file and text.
    """

    class Meta:
        model = models.ProductImage

    product = factory.SubFactory("products.tests.factories.ProductFactory")
    product_variant = None  # can override when needed
    image = factory.LazyAttribute(lambda _: ContentFile(fake.image(image_format="jpeg"), name="test.jpg"))
    alt_text = factory.LazyAttribute(lambda _: fake.sentence(nb_words=4))
    is_primary = False
    position = factory.Sequence(lambda n: n)


class ProductStockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductStock

    product = factory.SubFactory(ProductFactory)
    product_variant = None
    quantity = 10
    reserved = 0