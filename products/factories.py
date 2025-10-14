from django.utils.text import slugify
import factory
from faker import Faker

from . import models

fake = Faker()


class ProductCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductCategory

    class Params:
        is_root = True  # controls parent creation

    title = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.LazyAttribute(lambda obj: slugify(obj.title))
    description = factory.Faker("sentence")
    is_active = True

    @factory.lazy_attribute
    def parent(self):
        if self.is_root:
            return None
        return ProductCategoryFactory(is_root=True)

    @factory.post_generation
    def children(self, create, extracted, **kwargs):
        if not create or not extracted:
            return
        for _ in range(extracted):
            ProductCategoryFactory(parent=self)


class ProductTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductType

    title = factory.Faker("word")
    has_variants = factory.Faker("boolean")


class ProductAttributeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductAttribute

    title = factory.Faker("word")
    scope = factory.Iterator([models.ProductAttribute.Scope.PRODUCT, models.ProductAttribute.Scope.VARIANT])


class ProductTypeAttributeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductTypeAttribute

    product_type = factory.SubFactory(ProductTypeFactory)
    product_attribute = factory.SubFactory(ProductAttributeFactory)
    required = factory.Faker("boolean")
