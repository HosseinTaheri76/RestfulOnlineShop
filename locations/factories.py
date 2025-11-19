import factory

from .models import Province, City


class ProvinceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Province

    title = factory.Sequence(lambda n: f"Province {n}")


class CityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = City

    title = factory.Sequence(lambda n: f"City {n}")
    province = factory.SubFactory(ProvinceFactory)
