from django.contrib import admin
from django.db.models import Q
from mptt.admin import DraggableMPTTAdmin

from .models import (
    ProductCategory,
    ProductType,
    ProductAttribute,
    ProductAttributeOption,
    ProductTypeAttribute,
    Product,
    ProductSKU,
    ProductBrand,
    ProductSKUAttributeValue, ProductStock, ProductImage,
)

@admin.register(ProductBrand)
class BrandAdmin(admin.ModelAdmin):
    pass


class ProductStockInline(admin.TabularInline):
    model = ProductStock
    extra = 0

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0

# ================================================================
# CATEGORY ADMIN (MPTT)
# ================================================================
@admin.register(ProductCategory)
class CategoryAdmin(DraggableMPTTAdmin):
    mptt_indent_field = "title"
    list_display = ("tree_actions", "indented_title", "is_active")
    list_display_links = ("indented_title",)
    list_filter = ("is_active",)
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}


# ================================================================
# PRODUCT ATTRIBUTE OPTION INLINE
# ================================================================
class ProductAttributeOptionInline(admin.TabularInline):
    model = ProductAttributeOption
    extra = 1
    show_change_link = True


# ================================================================
# PRODUCT ATTRIBUTE ADMIN
# ================================================================
@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ("title", "scope")
    list_filter = ("scope",)
    search_fields = ("title",)
    inlines = [ProductAttributeOptionInline]


# ================================================================
# PRODUCT TYPE ATTRIBUTE INLINE
# ================================================================
class ProductTypeAttributeInline(admin.TabularInline):
    model = ProductTypeAttribute
    extra = 1

    # IMPORTANT: prevent scope mismatch in admin
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "product_attribute":
            obj_id = request.resolver_match.kwargs.get("object_id")
            if obj_id:
                pt = ProductType.objects.filter(pk=obj_id).first()
                if pt and not pt.has_variants:
                    kwargs["queryset"] = ProductAttribute.objects.filter(scope="product")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ================================================================
# PRODUCT TYPE ADMIN
# ================================================================
@admin.register(ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    list_display = ("title", "product_category", "has_variants")
    list_filter = ("product_category", "has_variants")
    search_fields = ("title", )
    inlines = [ProductTypeAttributeInline]

    # Ensure only attributes belonging to this category are selectable
    def save_model(self, request, obj, form, change):
        obj.save()


# ================================================================
# PRODUCT SKU ATTRIBUTE INLINE
# ================================================================
class ProductSKUAttributeValueInline(admin.TabularInline):
    model = ProductSKUAttributeValue
    extra = 1

    # Filter attribute options by type-level definition
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "product_attribute_option":
            # read parent object (SKU)
            object_id = request.resolver_match.kwargs.get("object_id")
            if object_id:
                sku = ProductSKU.objects.filter(pk=object_id).first()
                if sku:
                    kwargs["queryset"] = ProductAttributeOption.objects.filter(
                        product_attribute__in=ProductTypeAttribute.objects.filter(
                            product_type=sku.product.product_type
                        ).values("product_attribute")
                    )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ================================================================
# PRODUCT SKU ADMIN
# ================================================================
@admin.register(ProductSKU)
class ProductSKUAdmin(admin.ModelAdmin):
    list_display = ("product", "title", "sku", "is_active")
    list_filter = ("is_active", "product__product_type")
    search_fields = ("title", "sku")
    inlines = [ProductStockInline, ProductImageInline, ProductSKUAttributeValueInline]


# ================================================================
# PRODUCT ADMIN
# ================================================================
class ProductSKUInline(admin.TabularInline):
    model = ProductSKU
    extra = 1
    show_change_link = True

    # If product_type.has_variants=False → hide SKU inline completely
    def has_view_or_change_permission(self, request, obj=None):
        if obj and not obj.product_type.has_variants:
            return False
        return True


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "product_category", "product_type", "is_active")
    list_filter = ("product_category", "product_type", "is_active")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ProductSKUAttributeValueInline, ProductSKUInline]

    # Filter product types based on selected category
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "product_type":
            if "product_category" in request.GET:
                cat_id = request.GET.get("product_category")
                kwargs["queryset"] = ProductType.objects.filter(product_category_id=cat_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

