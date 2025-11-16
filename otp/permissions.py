from rest_framework.permissions import BasePermission
from rest_framework.exceptions import NotFound, PermissionDenied
from otp.models import OTPGrant


class OTPGrantRequired(BasePermission):

    def has_permission(self, request, view):
        # Your view must define a purpose
        assert getattr(view, "purpose"), "View must define `purpose`"
        assert "grant_id" in view.kwargs, "`grant_id` must be in URL kwargs"

        grant_id = view.kwargs["grant_id"]

        # --- Case 1: Grant does not exist -> 404 ---
        try:
            grant = OTPGrant.objects.get(pk=grant_id)
        except OTPGrant.DoesNotExist:
            raise NotFound("OTP grant not found.")

        # --- Case 2: Wrong purpose OR unusable (expired/consumed) -> 403 ---
        if grant.purpose != view.purpose:
            raise PermissionDenied("Invalid OTP grant purpose.")

        if not grant.is_usable():
            raise PermissionDenied("OTP grant is expired or already used.")

        # --- Case 3: Everything OK ---
        view.grant = grant
        return True