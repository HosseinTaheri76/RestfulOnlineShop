from django.contrib import admin

from . import models



# ─────────────────────────────────────────────
# Inline for attribute values (used by Product & Variant)
# ─────────────────────────────────────────────

class ProductSKUAttributeValueInline(admin.TabularInline):
    model = models.ProductSKUAttributeValue
    extra = 1
    fields = ("product_type_attribute", "value", "product_variant")
    autocomplete_fields = ("product_type_attribute", "value", "product_variant")

    def get_queryset(self, request):
        # Optimize query for admin
        return (
            super()
            .get_queryset(request)
            .select_related(
                "product",
                "product_variant",
                "product_type_attribute__product_attribute",
                "value",
            )
        )

    def get_formset(self, request, obj=None, **kwargs):
        """
        Customizes formset behavior depending on whether it's used in ProductAdmin or ProductVariantAdmin.
        """
        formset = super().get_formset(request, obj, **kwargs)
        if isinstance(obj, models.Product):
            # When editing a Product, only allow product-wide attributes
            formset.form.base_fields["product_variant"].required = False
        elif isinstance(obj, models.ProductVariant):
            # When editing a Variant, restrict attribute values to its product only
            formset.form.base_fields["product_variant"].queryset = (
                models.ProductVariant.objects.filter(product=obj.product)
            )
        return formset


# ─────────────────────────────────────────────
# Product Variant Admin
# ─────────────────────────────────────────────

@admin.register(models.ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("sku", "product", "is_active")
    list_filter = ("is_active",)
    search_fields = ("sku", "product__title")
    autocomplete_fields = ("product",)
    inlines = [ProductSKUAttributeValueInline]


# ─────────────────────────────────────────────
# Product Admin
# ─────────────────────────────────────────────

@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "product_type", "product_category", "is_active")
    list_filter = ("product_type", "product_category", "is_active")
    search_fields = ("title", "slug")
    autocomplete_fields = ("product_type", "product_category")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ProductSKUAttributeValueInline]


# ─────────────────────────────────────────────
# Supporting Admins
# ─────────────────────────────────────────────

@admin.register(models.ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    list_display = ("title", "has_variants")
    list_filter = ("has_variants",)
    search_fields = ("title",)


@admin.register(models.ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ("title", "scope", "filterable")
    list_filter = ("scope", "filterable")
    search_fields = ("title",)


@admin.register(models.ProductAttributeOption)
class ProductAttributeOptionAdmin(admin.ModelAdmin):
    list_display = ("product_attribute", "value")
    search_fields = ("value", "product_attribute__title")
    autocomplete_fields = ("product_attribute",)


@admin.register(models.ProductTypeAttribute)
class ProductTypeAttributeAdmin(admin.ModelAdmin):
    list_display = ("product_type", "product_attribute", "required")
    search_fields = ("product_type__title", "product_attribute__title")
    list_filter = ("product_type", "required")
    autocomplete_fields = ("product_type", "product_attribute")


@admin.register(models.ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("title", "parent", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}
