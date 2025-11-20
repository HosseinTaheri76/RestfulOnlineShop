from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import Province, City


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ['id', 'title', 'is_active']


class ProvinceSerializer(serializers.ModelSerializer):
    cities = CitySerializer(
        label=_('cities'),
        many=True,
        read_only=True
    )

    class Meta:
        model = Province
        fields = ['id', 'title', 'is_active', 'cities']
