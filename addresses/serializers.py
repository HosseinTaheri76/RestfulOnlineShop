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

        instance = getattr(self, 'instance', None)

        # If updating, use the real instance
        # If creating, use a blank instance
        tmp = instance if instance is not None else UserAddress()

        # Ensure user is always present
        tmp.user = self.user

        # Apply only updated fields
        for key, value in attrs.items():
            setattr(tmp, key, value)

        # Run Django model-level validation
        tmp.full_clean()

        return attrs
