from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import UserAddress


@admin.register(UserAddress)
class UserAddressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "title",
        "recipient_name_display",
        "recipient_phone_display",
        "province",
        "city",
        "is_default",
        "postal_code",
    )
    list_filter = (
        "province",
        "city",
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
    readonly_fields = (
        "recipient_name_display",
        "recipient_phone_display",
    )

    fieldsets = (
        (_("User"), {
            "fields": ("user", "title", "is_default"),
        }),
        (_("Recipient"), {
            "fields": (
                "recipient_full_name",
                "recipient_name_display",
                "recipient_phone",
                "recipient_phone_display",
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

    # -------------------------
    # Computed fields (readonly)
    # -------------------------
    def recipient_name_display(self, obj):
        return obj.get_recipient_full_name()
    recipient_name_display.short_description = _("Recipient (final)")

    def recipient_phone_display(self, obj):
        return obj.get_recipient_phone()
    recipient_phone_display.short_description = _("Phone (final)")
