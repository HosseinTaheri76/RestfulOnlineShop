from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import UserAddress


@admin.register(UserAddress)
class UserAddressAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "user",
        "province",
        "city",
        "is_default",
        "postal_code",
    )
    list_filter = (
        "province",
        "is_default",
    )
    search_fields = (
        "title",
        "street",
        "address_line_2",
        "recipient_full_name",
        "recipient_phone",
        "postal_code",
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
    )
    autocomplete_fields = ("user", "province", "city")
    list_editable = ("is_default",)

    fieldsets = (
        (_("User"), {
            "fields": ("user", "title", "is_default"),
        }),
        (_("Recipient"), {
            "fields": (
                "recipient_full_name",
                "recipient_phone",
            )
        }),
        (_("Address"), {
            "fields": (
                "province",
                "city",
                "street",
                "address_line_2",
                ("building_number", "unit_number"),
                "postal_code",
            )
        }),
    )
