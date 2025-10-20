from django.contrib import admin

from mptt import admin as mptt_admin

from products import models

# ─────────────────────────────────────────────
# INLINE ADMINS
# ─────────────────────────────────────────────

class ProductAttributeOptionInline(admin.TabularInline):
    model = models.ProductAttributeOption
    extra = 0
    max_num = 1


class ProductTypeAttributeInline(admin.TabularInline):
    model = models.ProductTypeAttribute
    extra = 1
    min_num = 1


class ProductVariantInline(admin.TabularInline):
    model = models.ProductVariant
    extra = 0
    min_num = 1

class ProductSkuAttributeValueInline(admin.TabularInline):
    model = models.ProductSKUAttributeValue
    extra = 0
    show_change_link = True
    can_delete = True

    def get_exclude(self, request, obj=None):
        """Hide product or variant field depending on context."""
        if isinstance(obj, models.ProductVariant):
            return ["product"]
        if isinstance(obj, models.Product):
            return ["product_variant"]
        return []

class ProductImageInline(admin.TabularInline):
    model = models.ProductImage
    extra = 0

    def get_exclude(self, request, obj=None):
        """Hide product or variant field depending on context."""
        if isinstance(obj, models.ProductVariant):
            return ["product"]
        if isinstance(obj, models.Product):
            return ["product_variant"]
        return []

# ─────────────────────────────────────────────
# MAIN ADMINS
# ─────────────────────────────────────────────

@admin.register(models.ProductCategory)
class ProductCategoryAdmin(mptt_admin.MPTTModelAdmin):
    mptt_level_indent = 20
    list_display = ["title", "is_active"]
    list_editable = ["is_active"]
    list_filter = ["is_active"]
    search_fields = ["title", "slug"]
    prepopulated_fields = {"slug": ("title",)}

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("parent")


@admin.register(models.ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    list_display = ["title", "has_variants"]
    list_filter = ["has_variants"]
    search_fields = ["title"]
    inlines = [ProductTypeAttributeInline]


@admin.register(models.ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ["title", "scope", "filterable"]
    list_editable = ["filterable"]
    list_filter = ["scope", "filterable"]
    search_fields = ["title"]
    inlines = [ProductAttributeOptionInline]


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["title", "price", "is_active"]
    list_editable = ["is_active"]
    list_filter = ["is_active"]
    search_fields = ["title", "product_type__title", "product_category__title"]
    inlines = [ProductImageInline, ProductSkuAttributeValueInline]

    def get_inlines(self, request, obj):
        """Dynamically add variants inline only when needed."""
        inlines = super().get_inlines(request, obj).copy()
        if obj and obj.product_type.has_variants:
            inlines.append(ProductVariantInline)
        return inlines

@admin.register(models.ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ["product", "sku", "title", "price", "is_active"]
    list_editable = ["is_active"]
    list_filter = ["is_active"]
    search_fields = ["product__title", "sku", "title"]
    inlines = [ProductImageInline, ProductSkuAttributeValueInline]

    def save_formset(self, request, form, formset, change):
        """Ensure inline ProductSKUAttributeValue links to correct product + variant."""
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(formset.model, (models.ProductSKUAttributeValue, models.ProductImage)):
                instance.product_variant = form.instance
                instance.product = form.instance.product
            instance.full_clean()
            instance.save()
        formset.save_m2m()

