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



