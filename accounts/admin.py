from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for the custom User model."""

    # Fields displayed in user list
    list_display = (
        "username",
        "email",
        "email_verified",
        "phone_number",
        "phone_number_verified",
        "is_staff",
        "is_active",
    )
    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
        "email_verified",
        "phone_number_verified",
    )

    # For searching users in admin
    search_fields = (
        "username",
        "email",
        "phone_number",
        "first_name",
        "last_name",
    )

    ordering = ("id",)

    readonly_fields = ("last_login", "date_joined")

    # -----------------------------
    # Fieldsets for editing a user
    # -----------------------------
    fieldsets = (
        (_("Login Credentials"), {
            "fields": (
                "username",
                "password",
            )
        }),
        (_("Personal Information"), {
            "fields": (
                "first_name",
                "last_name",
                "email",
                "email_verified",
                "phone_number",
                "phone_number_verified",
            )
        }),
        (_("Permissions"), {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            )
        }),
        (_("Important Dates"), {
            "fields": (
                "last_login",
                "date_joined",
            )
        }),
    )

    # -----------------------------
    # Fieldsets for "Add user" page
    # -----------------------------
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "username",
                "password1",
                "password2",
                "email",
                "phone_number",
                "is_staff",
                "is_active",
            ),
        }),
    )
