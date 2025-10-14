from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from mptt.admin import MPTTModelAdmin
from django.utils.text import slugify

from . import models


# inlines
class ProductTypeAttributeInline(admin.TabularInline):
    model = models.ProductTypeAttribute
    extra = 1
    min_num = 1


class ProductAttributeOptionInline(admin.TabularInline):
    model = models.ProductAttributeOption
    extra = 1
    min_num = 1


@admin.register(models.ProductCategory)
class ProductCategoryAdmin(MPTTModelAdmin):
    """
    Hierarchical category admin using django-mptt's tree UI.
    """
    mptt_level_indent = 20  # visual indentation per level

    # --- Display ---
    list_display = (
        "indented_title",
        "slug",
        "is_active",
        "parent",
    )
    list_display_links = ("indented_title",)
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    search_fields = ("title", "slug", "description")
    ordering = ("tree_id", "lft")  # natural tree order

    # --- Form options ---
    prepopulated_fields = {"slug": ("title",)}
    list_select_related = ("parent",)
    readonly_fields = ("full_path_display",)

    fieldsets = (
        (None, {
            "fields": (
                "parent",
                "title",
                "slug",
                "description",
                "is_active",
            )
        }),
    )

    # --- Custom display methods ---
    def indented_title(self, obj):
        """Show the title indented according to tree level."""
        return f"{'— ' * obj.level}{obj.title}"

    indented_title.short_description = _("Category")

    def full_path_display(self, obj):
        """Show the full hierarchical path."""
        return obj.full_path

    full_path_display.short_description = _("Full path")

    # --- Save logic ---
    def save_model(self, request, obj, form, change):
        """
        Auto-fill slug if not set.
        Depth & activation validation handled by model.
        """
        if not obj.slug:
            obj.slug = slugify(obj.title)
        super().save_model(request, obj, form, change)

    # --- Query optimization ---
    def get_queryset(self, request):
        """Ensure related parent data is fetched efficiently."""
        qs = super().get_queryset(request)
        return qs.select_related("parent")


@admin.register(models.ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    inlines = (ProductTypeAttributeInline,)


@admin.register(models.ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    inlines = (ProductAttributeOptionInline,)
