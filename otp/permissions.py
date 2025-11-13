from rest_framework.permissions import BasePermission

from .models import OTPGrant


class OTPGrantRequired(BasePermission):

    def has_permission(self, request, view):
        assert getattr(view, 'purpose')
        assert 'grant_id' in view.kwargs
        try:
            grant = OTPGrant.objects.get(pk=view.kwargs['grant_id'])
            if grant.purpose != view.purpose or not grant.is_usable():
                return False
            view.grant = grant
            return True
        except OTPGrant.DoesNotExist:
            return False
