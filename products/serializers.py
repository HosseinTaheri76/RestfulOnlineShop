from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from . import models, queries


# ─────────────────────────────────────────────
#  Product Attribute Option
# ─────────────────────────────────────────────
class ProductAttributeOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProductAttributeOption
        fields = ["id", "value"]
        read_only_fields = fields


# ─────────────────────────────────────────────
#  Product Attribute
# ─────────────────────────────────────────────
class ProductAttributeSerializer(serializers.ModelSerializer):
    options = ProductAttributeOptionSerializer(
        many=True,
        read_only=True,
        source="prefetched_options",
        label=_("options"),
    )

    class Meta:
        model = models.ProductAttribute
        fields = ["id", "title", "options"]
        read_only_fields = fields


# ─────────────────────────────────────────────
#  Product Image
# ─────────────────────────────────────────────
class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField(label=_("image URL"))

    class Meta:
        model = models.ProductImage
        fields = ["id", "alt_text", "is_primary", "image"]
        read_only_fields = fields

    def get_image(self, obj):
        """Return absolute image URL if request exists."""
        request = self.context.get("request")
        url = getattr(obj.image, "url", None)
        if url and request:
            return request.build_absolute_uri(url)
        return url


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
        fields = ["id", "attribute", "value"]
        read_only_fields = fields


# ─────────────────────────────────────────────
#  Product Category (recursive)
# ─────────────────────────────────────────────
class ProductCategorySerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField(label=_("URL"))
    sub_categories = serializers.SerializerMethodField(label=_("sub categories"))

    class Meta:
        model = models.ProductCategory
        fields = ["id", "title", "url", "description", "sub_categories"]
        read_only_fields = fields

    def get_url(self, product_category):
        request = self.context.get("request")
        url = product_category.get_absolute_url()
        return request.build_absolute_uri(url) if request else url

    def get_sub_categories(self, category):
        """Return serialized subcategories if not at max depth."""
        if category.level >= category.MAX_LEVEL:
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
        read_only_fields = fields


# ─────────────────────────────────────────────
#  Product List
# ─────────────────────────────────────────────
class ProductListSerializer(serializers.ModelSerializer):
    thumbnail = serializers.SerializerMethodField(label=_("thumbnail"))
    url = serializers.SerializerMethodField(label=_("URL"))
    product_brand = serializers.StringRelatedField(label=_("product brand"))
    price = serializers.DecimalField(
        source="effective_price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
        label=_("price"),
    )

    class Meta:
        model = models.Product
        fields = ["id", "title", "product_brand", "url", "price", "is_available", "thumbnail"]
        read_only_fields = fields

    def get_thumbnail(self, product):
        request = self.context.get("request")
        url = product.thumbnail_image_url
        return request.build_absolute_uri(url) if request and url else url

    def get_url(self, product):
        request = self.context.get("request")
        url = product.get_absolute_url()
        return request.build_absolute_uri(url) if request else url


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
    category = serializers.StringRelatedField(
        source="product_category",
        read_only=True,
        label=_("category"),
    )
    brand = serializers.StringRelatedField(
        source="product_brand",
        read_only=True,
        label=_("brand"),
    )

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "category",
            "brand",
            "description",
            "images",
            "specifications",
            "variants",
        ]
        read_only_fields = fields

class ProductCompareSerializer(serializers.Serializer):
    """
    Serializer that validates product IDs and returns structured comparison data.
    """

    product_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        min_length=2,
        max_length=5,
    )

    # ─────────────────────────────────────────────
    # Validation
    # ─────────────────────────────────────────────
    @staticmethod
    def validate_product_ids(values):
        """
        Ensure all provided product IDs are valid, unique,
        active, and belong to the same product type.
        """
        if len(values) < 2:
            raise serializers.ValidationError(_("At least two products are required for comparison."))

        if len(values) != len(set(values)):
            raise serializers.ValidationError(_("Product IDs must be unique."))

        products = models.Product.active.only("id", "product_type_id").filter(id__in=values)
        found_ids = {p.id for p in products}

        if found_ids != set(values):
            raise serializers.ValidationError(_("Some provided products do not exist or are inactive."))

        type_ids = {p.product_type_id for p in products}
        if len(type_ids) > 1:
            raise serializers.ValidationError(_("All products must share the same product type."))

        return values

    # ─────────────────────────────────────────────
    # Representation
    # ─────────────────────────────────────────────
    def to_representation(self, instance):
        """
        Override the default representation to directly return comparison data.
        """
        return self.get_comparison_data()

    # ─────────────────────────────────────────────
    # Core comparison logic
    # ─────────────────────────────────────────────
    def get_comparison_data(self):
        """
        Build a structured dataset for comparing the validated products.
        """
        product_ids = self.validated_data["product_ids"]
        products = queries.get_product_queryset(prefetch_attribute_values=True).filter(id__in=product_ids)
        result = {"products": ProductListSerializer(products, many=True, context=self.context).data}
        # Temporary structure: {attribute_title: {product_id: value or [values]}}
        attribute_map = {}

        for product in products:
            # Product-level attributes (apply to all variants)
            for pav in product.prefetched_attribute_values:
                attr_title = pav.value.product_attribute.title
                attr_value = pav.value.value
                attribute_map.setdefault(attr_title, {})[product.id] = attr_value

            # Variant-level attributes (specific to SKUs)
            for variant in product.prefetched_variants:
                for pav in variant.prefetched_attribute_values:
                    attr_title = pav.value.product_attribute.title
                    attr_value = pav.value.value
                    product_attrs = attribute_map.setdefault(attr_title, {})
                    product_attrs.setdefault(product.id, []).append(attr_value)

        specifications = []
        for attr_title, product_values in attribute_map.items():
            # Determine placeholder type
            sample_value = next(iter(product_values.values()))
            placeholder = [] if isinstance(sample_value, list) else ""

            # Ensure consistent product order and fill missing entries
            values = [product_values.get(pid, placeholder) for pid in product_ids]

            # Mark if the values differ between products
            differs = all(values) and len(set(map(str, values))) > 1

            specifications.append({
                "title": attr_title,
                "values": values,
                "differs": differs,
            })

        result["specifications"] = specifications
        return result
