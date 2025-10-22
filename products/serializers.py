from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from . import models


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProductImage
        fields = ["id", "alt_text", "is_primary", "image"]


class ProductSKUAttributeValueSerializer(serializers.ModelSerializer):
    attribute = serializers.CharField(
        read_only=True,
        label=_("attribute"),
        source="value.product_attribute"
    )
    value = serializers.CharField(
        read_only=True,
        label=_("value"),
        source="value.value"
    )

    class Meta:
        model = models.ProductSKUAttributeValue
        fields = ["id", "attribute", "value"]


class ProductVariantSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(
        many=True,
        read_only=True,
        label=_("images")
    )
    is_available = serializers.SerializerMethodField(
        label=_("is_available"),
    )
    specifications = ProductSKUAttributeValueSerializer(
        many=True,
        read_only=True,
        label=_("specification"),
        source="attribute_values"
    )

    class Meta:
        model = models.ProductVariant
        fields = ["id", "sku", "title", "price", "is_primary", "is_available", "images", "specifications"]

    @staticmethod
    def get_is_available(obj):
        return obj.is_available


class ProductCategorySerializer(serializers.ModelSerializer):
    sub_categories = serializers.SerializerMethodField(label=_("sub categories"), read_only=True)

    class Meta:
        model = models.ProductCategory
        fields = ["id", "title", "description", "sub_categories"]

    def get_sub_categories(self, product_category):
        # Use prefetched cache instead of triggering a new query
        if product_category.level == models.ProductCategory.MAX_LEVEL:
            return []

        children = getattr(product_category, "_prefetched_objects_cache", {}).get("children")

        if children is None:
            # fallback if prefetch not applied (e.g. single detail view)
            children = product_category.children(manager='active').get_queryset()

        return ProductCategorySerializer(children, many=True, context=self.context).data


class ProductListSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField(label=_("price"))
    is_available = serializers.SerializerMethodField(label=_("is available"))
    thumbnail = serializers.SerializerMethodField(label=_("thumbnail"))

    class Meta:
        model = models.Product
        fields = ["id", "title", "price", "is_available", "thumbnail"]

    @staticmethod
    def get_price(product):
        return product.effective_price

    @staticmethod
    def get_is_available(product):
        return product.is_available

    def get_thumbnail(self, product):
        image_url = product.thumbnail_url
        request = self.context.get("request")
        if image_url:
            return request.build_absolute_uri(image_url)
        return ""


class ProductDetailSerializer(ProductListSerializer):

    images = serializers.SerializerMethodField(
        label=_("images"),
        read_only=True,
    )
    specifications = serializers.SerializerMethodField(
        label=_("specifications"),
        read_only=True,
    )
    variants = serializers.SerializerMethodField(
        label=_("variants"),
        read_only=True,
    )

    class Meta:
        model = models.Product
        fields = ProductListSerializer.Meta.fields + [
            "product_category",
            "description",
            "images",
            "specifications",
            "variants"
        ]

    def get_images(self, product):
        qs = product.images.filter(product_variant__isnull=True)
        return ProductImageSerializer(qs, many=True, context=self.context).data

    def get_specifications(self, product):
        qs = product.attribute_values.filter(product_variant__isnull=True)
        return ProductSKUAttributeValueSerializer(qs, many=True, context=self.context).data

    def get_variants(self, product):
        qs = product.variants(manager='active').all()
        return ProductVariantSerializer(qs, many=True, context=self.context).data