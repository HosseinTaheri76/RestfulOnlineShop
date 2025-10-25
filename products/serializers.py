from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from . import models


# ─────────────────────────────────────────────
#  Product Image
# ─────────────────────────────────────────────

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProductImage
        fields = [
            "id",
            "alt_text",
            "is_primary",
            "image"
        ]


# ─────────────────────────────────────────────
#  Product SKU Attribute Value
# ─────────────────────────────────────────────

class ProductSKUAttributeValueSerializer(serializers.ModelSerializer):
    attribute = serializers.CharField(
        source="value.product_attribute",
        read_only=True,
        label=_("attribute"),
    )
    value = serializers.CharField(
        source="value.value",
        read_only=True,
        label=_("value"),
    )

    class Meta:
        model = models.ProductSKUAttributeValue
        fields = [
            "id",
            "attribute",
            "value"
        ]


# ─────────────────────────────────────────────
#  Product Category (recursive)
# ─────────────────────────────────────────────

class ProductCategorySerializer(serializers.ModelSerializer):
    sub_categories = serializers.SerializerMethodField(label=_("sub categories"))

    class Meta:
        model = models.ProductCategory
        fields = ["id", "title", "description", "sub_categories"]

    def get_sub_categories(self, category):
        """Return serialized subcategories if not at max depth."""
        if category.level >= self.Meta.model.MAX_LEVEL:
            return []

        children = getattr(category, "prefetched_children", [])

        return ProductCategorySerializer(children, many=True, context=self.context).data


# ─────────────────────────────────────────────
#  Product Variant
# ─────────────────────────────────────────────

class ProductVariantSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(
        many=True,
        read_only=True,
        source="prefetched_images",
        label=_("images"),
    )
    specifications = ProductSKUAttributeValueSerializer(
        many=True,
        read_only=True,
        source="prefetched_attribute_values",
        label=_("specifications"),
    )

    class Meta:
        model = models.ProductVariant
        fields = [
            "id",
            "sku",
            "title",
            "price",
            "is_primary",
            "is_available",
            "images",
            "specifications",
        ]


# ─────────────────────────────────────────────
#  Product List
# ─────────────────────────────────────────────

class ProductListSerializer(serializers.ModelSerializer):
    thumbnail = serializers.SerializerMethodField(label=_("thumbnail"))

    price = serializers.DecimalField(
        source="effective_price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
        label=_("price"),
    )

    class Meta:
        model = models.Product
        fields = [
            "id",
            "title",
            "price",
            "is_available",
            "thumbnail"
        ]

    def get_thumbnail(self, product):
        request = self.context.get("request")
        thumbnail = product.thumbnail_image_url
        if request:
            return request.build_absolute_uri(thumbnail)
        return thumbnail


# ─────────────────────────────────────────────
#  Product Detail
# ─────────────────────────────────────────────

class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(
        many=True,
        read_only=True,
        source="prefetched_images",
        label=_("images"),
    )
    specifications = ProductSKUAttributeValueSerializer(
        many=True,
        read_only=True,
        source="prefetched_attribute_values",
        label=_("specifications"),
    )
    variants = ProductVariantSerializer(
        many=True,
        read_only=True,
        source="prefetched_variants",
        label=_("variants"),
    )

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "product_category",
            "description",
            "images",
            "specifications",
            "variants",
        ]
