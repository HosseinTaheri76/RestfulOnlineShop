from django.core.exceptions import ValidationError
from rest_framework import serializers

from .models import UserAddress


class UserAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAddress
        fields = [
            'id',
            'title',
            'recipient_full_name',
            'recipient_phone',
            'province',
            'city',
            'street',
            'address_line_2',
            'building_number',
            'unit_number',
            'postal_code',
            'is_default'
        ]

    @property
    def user(self):
        return self.context['request'].user

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Determine instance (create/update)
        instance = getattr(self, 'instance', None)
        # Create a temporary model instance to validate
        tmp = UserAddress(**{**(instance.to_dict() if instance else {}), **attrs}, user=self.user)
        # Call Django's model-level validation
        tmp.full_clean()
        return attrs
