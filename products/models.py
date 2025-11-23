from typing import Optional, Set
from functools import cached_property

from django.db import models, transaction
from django.db.models import Q, F
from django.db.models.aggregates import Max
from django.db.models.functions.text import Lower
from django.urls.base import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from model_utils import FieldTracker
from mptt.models import MPTTModel, TreeForeignKey, TreeManager

from utils.models.helpers import SlugModelMixin, get_prefetched
from utils.models.validation import ModelValidationMixin, skip_if_missing_fields


class ActiveCategoryManager(TreeManager):

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class ActiveProductManager(models.Manager):

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True, product_category__is_active=True)


class ActiveSKUManager(models.Manager):

    def get_queryset(self):
        return super().get_queryset().filter(
            is_active=True,
            product__is_active=True,
            product__product_category__is_active=True
        )


class Category(ModelValidationMixin, SlugModelMixin, MPTTModel):
    MAX_LEVEL = 2

    parent = TreeForeignKey(
        to="self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sub_categories",
        limit_choices_to=Q(level__lt=MAX_LEVEL),
        verbose_name=_("parent"),
    )
    title = models.CharField(
        unique=True,
        max_length=255,
        verbose_name=_("title")
    )
    description = models.TextField(
        blank=True,
        max_length=500,
        verbose_name=_("description")
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("active")
    )

    objects = TreeManager()
    active = ActiveCategoryManager()

    _tracker = FieldTracker(fields=["parent_id", "is_active"])

    class MPTTMeta:
        order_insertion_by = ["title"]

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")

    def __str__(self):
        return self.title

    @transaction.atomic
    def save(self, *args, **kwargs) -> None:
        self._handle_activation()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse('products:product-list-by-category', kwargs={"product_category_slug": self.slug})

    @transaction.atomic
    def delete(self, *args, **kwargs) -> None:
        if self.is_active and self.parent:
            self._deactivate_ancestors_if_has_no_active_descendants(self)
        super().delete(*args, **kwargs)

    def _validate_depth(self) -> None:

        if not self.parent:
            return

        error_msg = _("The category \"%(category)s\" cannot accept subcategories due to category depth limit.")

        if not self.pk or self.is_leaf_node():
            if self.parent.level >= self.MAX_LEVEL:
                raise ValidationError({"parent": error_msg % {"category": self.parent}})
            return

        max_descendant_level = self.get_descendants().aggregate(max_level=Max("level"))["max_level"] or self.level

        distance_to_farthest = max_descendant_level - self.level

        resulting_deepest = self.parent.level + distance_to_farthest + 1

        if resulting_deepest > self.MAX_LEVEL:
            raise ValidationError({"parent": error_msg % {"category": self.parent}})

    def _validate_categories_with_products_cannot_accept_subcategories(self):

        if self.parent and self.parent.products.exists():
            raise ValidationError(_("A category that contains products cannot have subcategories."))

    @staticmethod
    def _deactivate_ancestors_if_has_no_active_descendants(node):

        ancestors = list(node.get_ancestors().prefetch_related("sub_categories").all())
        to_deactivate = set()
        to_deactivate.add(node.pk)

        for anc in reversed(ancestors):
            children = list(anc.sub_categories.all())

            has_active_child_outside = any(
                (child.is_active and child.pk not in to_deactivate) for child in children
            )
            if not has_active_child_outside:
                to_deactivate.add(anc.pk)

        if to_deactivate:
            Category.objects.filter(pk__in=to_deactivate).update(is_active=False)

    def _handle_activation(self) -> None:

        is_update = bool(self.pk)
        parent_changed = self._tracker.has_changed("parent_id")
        is_active_changed = self._tracker.has_changed("is_active")
        prev_parent_id: Optional[int] = self._tracker.previous("parent_id") if is_update else None

        if not is_update:
            if self.is_active and self.parent:
                self.parent.get_ancestors(include_self=True).update(is_active=True)
            return

        if is_active_changed:
            if self.is_active:

                self.get_family().update(is_active=True)
            else:

                self.get_descendants().update(is_active=False)
                self._deactivate_ancestors_if_has_no_active_descendants(self)

        if parent_changed:

            if self.is_active and self.parent:
                self.parent.get_ancestors(include_self=True).update(is_active=True)

            if prev_parent_id:
                prev_parent = type(self).objects.filter(pk=prev_parent_id).first()
                if prev_parent:
                    self._deactivate_ancestors_if_has_no_active_descendants(prev_parent)


class ProductType(ModelValidationMixin, models.Model):
    """
    Represents a product schema defining which attributes and variant logic apply to products.

    Examples:
        - "Smartphone" (has variants like different storage or colors)
        - "Laptop" (no variants)
        - "T-Shirt" (variants by color and size)
    """
    product_category = models.ForeignKey(
        to=ProductCategory,
        on_delete=models.CASCADE,
        related_name="product_types",
        verbose_name=_("product category"),
        help_text=_(
            "Select the main category this product type belongs to. "
            "Products of this type will usually appear under this category, "
            "and its attributes will be used to build filters for products within it."
        ),
    )
    title = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("title"),
        help_text=_("A descriptive name for this product type (e.g., 'Smartphone', 'Laptop')."),
    )
    has_variants = models.BooleanField(
        default=False,
        verbose_name=_("has variants"),
        help_text=_(
            "Indicates whether products of this type can have multiple variants. "
            "If enabled, products under this type can define variant-specific attributes "
            "(e.g., color, size, storage) and each variant can have its own SKU, price, and stock. "
            "If disabled, products of this type are treated as single, non-variant items."
        ),
    )

    _tracker = FieldTracker(fields=["has_variants", "product_category"])

    def _validate_has_variants(self):
        """
        Prevent changing the 'has_variants' flag when products are already associated.

        Rationale:
          - Changing 'has_variants' affects the data model expectations.
          - If products already exist, flipping this flag would invalidate pricing
            and SKU consistency (e.g., products with variants shouldn't have a price
            or SKU, and single-variant products must have them).
          - Therefore, once products are linked to a type, this field becomes immutable.
        """

        if self.pk and self._tracker.has_changed("has_variants") and self.products.exists():
            raise ValidationError({
                "has_variants": _(
                    "Cannot change this field because products are already linked "
                    "to this type. The 'has_variants' flag is immutable once used."
                )
            })

    def _validate_product_category_change(self):
        if self.pk and self._tracker.has_changed("product_category") and self.products.exists():
            raise ValidationError(
                {'product_category': _(
                    "Product category cannot be changed "
                    "because products are linked with this type."
                )}
            )

    class Meta:
        verbose_name = _("Product Type")
        verbose_name_plural = _("Product Types")
        ordering = ["title"]

    def __str__(self):
        return self.title


class ProductBrand(SlugModelMixin, models.Model):
    title = models.CharField(
        max_length=128,
        unique=True,
        verbose_name=_("title"),
    )

    class Meta:
        verbose_name = _("Brand")
        verbose_name_plural = _("Brands")

    def __str__(self):
        return self.title


class ProductAttribute(ModelValidationMixin, models.Model):
    """
    Defines a characteristic that can describe a product or a variant.

    Attributes may be:
        - Product-level (shared by all variants, e.g., Brand, Screen Size)
        - Variant-level (differs per variant, e.g., Color, Size, Storage)
    """

    class Scope(models.TextChoices):
        PRODUCT = "product", _("Product")
        VARIANT = "variant", _("Variant")

    title = models.CharField(
        max_length=128,
        unique=True,
        verbose_name=_("title"),
        help_text=_("Human-readable name for this attribute (e.g., 'Color', 'Storage', 'Brand')."),
    )
    scope = models.CharField(
        max_length=10,
        choices=Scope.choices,
        verbose_name=_("scope"),
        help_text=_(
            "Defines whether this attribute applies to the product as a whole or to its variants. "
            "Product-level attributes are shared by all variants (e.g., Brand, CPU, Screen Size). "
            "Variant-level attributes can differ between variants (e.g., Color, Size, Storage)."
        ),
    )
    filterable = models.BooleanField(
        default=False,
        verbose_name=_("filterable"),
        help_text=_(
            "If enabled, this attribute will appear as a filter option in product listings "
            "and search pages. Use this for attributes that customers typically use to narrow down "
            "results (e.g., Color, Size, Brand). Attributes that are only descriptive "
            "(e.g., Model Number, Material Composition) should usually not be filterable."
        ),
    )

    _tracker = FieldTracker(fields=["scope", ])

    class Meta:
        verbose_name = _("Product Attribute")
        verbose_name_plural = _("Product Attributes")
        ordering = ["title"]

    def __str__(self):
        return self.title

    def _validate_scope_change(self):
        """
        Prevent changing the 'scope' of an attribute if it already has
        associated ProductSKUAttributeValue records.

        Example:
            - 'scope' determines whether the attribute applies to products or variants.
            - Once used in product or variant values, changing scope would cause inconsistency.
        """
        if not self.pk:
            return  # no existing record to validate

        if not self._tracker.has_changed("scope"):
            return  # scope isn't changed → safe

        # Check for existing usage efficiently
        linked_values_exist = (
            ProductSKUAttributeValue.objects
            .filter(product_type_attribute__product_attribute_id=self.pk)
            .only("pk")  # lightweight query
            .exists()
        )

        if linked_values_exist:
            raise ValidationError({
                "scope": _(
                    "You cannot change the scope of this attribute because "
                    "it is already used in one or more product or variant attribute values."
                )
            })


class ProductAttributeOption(ModelValidationMixin, models.Model):
    """
    Represents a selectable value (option) for a product attribute.

    For example,
      - If the attribute is "Color", options might be "Red", "Blue", "Green".
      - If the attribute is "Size", options might be "S", "M", "L", "XL".

    Each option belongs to a single ProductAttribute and defines one of its possible values.
    The combination of (product_attribute, value) must be unique to prevent duplicate options.
    """

    product_attribute = models.ForeignKey(
        to=ProductAttribute,
        on_delete=models.CASCADE,
        related_name='options',
        verbose_name=_("product attribute"),
    )
    value = models.CharField(
        max_length=128,
        verbose_name=_("value"),
    )

    _tracker = FieldTracker(fields=["product_attribute", "value", ])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("value"),
                "product_attribute",
                name="unique_attr_value_ci"
            )
        ]

    def __str__(self):
        return f"{self.product_attribute.title}: {self.value}"

    def _validate_change(self):
        if self.pk and self._tracker.changed() and self.productskuattributevalue_set.exists():
            raise ValidationError(_("Cannot modify an option that is in use by products"))


class ProductTypeAttribute(ModelValidationMixin, models.Model):
    """
    Defines the relationship between a ProductType and a ProductAttribute,
    specifying whether the attribute is required.

    This acts as a schema rule ensuring that only valid attributes can be assigned
    to a product type — for example, preventing variant-level attributes from being
    used on non-variant product types.
    """

    product_type = models.ForeignKey(
        to="ProductType",
        on_delete=models.CASCADE,
        related_name="type_attributes",
        verbose_name=_("product type"),
    )
    product_attribute = models.ForeignKey(
        to="ProductAttribute",
        on_delete=models.CASCADE,
        related_name="type_attributes",
        verbose_name=_("product attribute"),
    )
    required = models.BooleanField(
        default=False,
        verbose_name=_("required"),
        help_text=_(
            "If enabled, this attribute must have a value for every product or variant "
            "of this type. Leave unchecked for optional attributes. "
            "For example, 'Storage Size' might be required for all smartphone variants, "
            "while 'Color' might be optional."
        ),
    )

    _tracker = FieldTracker(fields=["product_type", "product_attribute", ])

    class Meta:
        verbose_name = _("Type Attribute")
        verbose_name_plural = _("Type Attributes")
        constraints = [
            models.UniqueConstraint(
                fields=["product_type", "product_attribute"],
                name="unique_type_attribute",
            ),
        ]
        ordering = ["product_type__title", "product_attribute__title"]

    def __str__(self):
        return f"{self.product_type.title} → {self.product_attribute.title}"

    # ------------------------------------------------------------------
    # Validation Logic
    # ------------------------------------------------------------------

    def _validate_change(self):
        if self.pk and self._tracker.changed() and self.productskuattributevalue_set.exists():
            raise ValidationError(_("Cannot modify a ProductTypeAttribute that is in use by products"))

    @skip_if_missing_fields('product_type', 'product_attribute')
    def _validate_scope_compatibility(self):
        """Ensure variant attributes aren't assigned to non-variant product types."""
        if (
                not self.product_type.has_variants
                and self.product_attribute.scope == self.product_attribute.Scope.VARIANT
        ):
            raise ValidationError({
                "product_attribute": _(
                    "This product type does not support variant-level attributes."
                )
            })


class Product(ModelValidationMixin, SlugModelMixin, models.Model):
    """
    The allowed attributes for a product are determined by its `product_type`,
    and it is classified under a `product_category` (MPTT tree).
    """

    product_type = models.ForeignKey(
        to=ProductType,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("product type"),
        help_text=_("Defines the type of product, determining allowed attributes and whether it can have variants."),
    )
    product_category = models.ForeignKey(
        to=ProductCategory,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("product category"),
        help_text=_("The hierarchical category this product belongs to."),
    )
    product_brand = models.ForeignKey(
        to=ProductBrand,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("product brand"),
    )
    title = models.CharField(
        max_length=255,
        unique=True,
        verbose_name=_("title"),
        help_text=_("The human-readable name of the product."),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("description"),
        help_text=_("Optional long-form description displayed on the product page."),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("is active"),
        help_text=_("Uncheck to hide this product from the storefront."),
    )

    _tracker = FieldTracker(fields=['product_type_id'])

    objects = models.Manager()
    active = ActiveProductManager()

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["title"]

    def __str__(self):
        return self.title

    @transaction.atomic
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._create_required_attributes()

    def get_absolute_url(self) -> str:
        """Return absolute URL."""
        return reverse('products:product-detail', kwargs={'product_slug': self.slug})

    # @cached_property
    # def primary_variant(self):
    #     if self.product_type.has_variants:
    #         variants = get_prefetched(
    #             obj=self,
    #             attr_name="prefetched_variants",
    #             fallback_qs=self.variants(manager='active').all()
    #         )
    #         return next(filter(lambda variant: variant.is_primary, variants), None)
    #     return None

    # @cached_property
    # def is_available(self):
    #     """
    #     Determines if the product (or any of its variants, if applicable) has available stock.
    #     Uses prefetched data when available to avoid extra queries.
    #     """
    #     if self.product_type.has_variants:
    #         variants = get_prefetched(obj=self, attr_name="prefetched_variants", fallback_qs=self.variants.all())
    #         for variant in variants:
    #             if variant.is_available:
    #                 return True
    #         return False
    #     stocks = get_prefetched(obj=self, attr_name="prefetched_stocks", fallback_qs=self.stocks.all())
    #     return bool(stocks) and stocks[0].available > 0
    #
    # @cached_property
    # def effective_price(self):
    #     """
    #     Returns the product's current sellable price.
    #     - For multi-variant products: returns the primary variant's price.
    #     - For single-variant products: returns the product's own price.
    #     Returns None if no price is applicable or the product is unavailable.
    #     """
    #     # Choose product or primary variant
    #     target = self.primary_variant if self.product_type.has_variants else self
    #     if not target:
    #         return None
    #
    #     # Skip unavailable items early
    #     if not self.is_available:
    #         return None
    #
    #     # Ensure price attribute exists and is valid
    #     return getattr(target, "price", None)
    #
    # @cached_property
    # def primary_image_url(self):
    #     images = get_prefetched(
    #         obj=self,
    #         attr_name="prefetched_images",
    #         fallback_qs=self.images.all()
    #     )
    #     primary_image = next((image for image in images if image.is_primary), None)
    #     return primary_image.image.url if primary_image else ""
    #
    # @cached_property
    # def thumbnail_image_url(self):
    #     """
    #     Returns the URL of the primary image for this product or its primary variant.
    #     Prefers product images; falls back to primary variant images if none exist.
    #     """
    #     product_primary_image = self.primary_image_url
    #
    #     if product_primary_image:
    #         return product_primary_image
    #     if self.primary_variant:
    #         return self.primary_variant.primary_image_url
    #     return ""

    @skip_if_missing_fields("product_category")
    def _validate_category_is_leaf_node(self):
        if not self.product_category.is_leaf_node():
            raise ValidationError({'product_category': _('Product category must be a leaf node')})

    @skip_if_missing_fields("product_category")
    def _validate_is_active(self):
        if self.is_active and not self.product_category.is_active:
            raise ValidationError({"is_active": _("Cannot activate product under inactive category.")})

    def _validate_product_type_change(self):
        if self.pk and self._tracker.has_changed("product_type_id"):
            raise ValidationError({"product_type": _("Cannot change product type after creation.")})

    def _validate_product_type_category(self):
        # Ensure product’s category aligns with product type’s category
        type_category = self.product_type.product_category
        if self.product_category and type_category:
            # Allow the category or any of its descendants
            if not (
                    self.product_category == type_category
                    or self.product_category.is_descendant_of(type_category)
            ):
                raise ValidationError(
                    {
                        "product_category": _(
                            "Product category must be the same as or a subcategory of the product type's category."
                        )
                    }
                )

    def _create_required_attributes(self):
        """
        Ensure all required PRODUCT-scope attributes exist.
        These apply to the product itself, not its variants.
        """
        required_attr_ids = set(
            ProductTypeAttribute.objects.filter(
                required=True,
                product_type=self.product_type,
                product_attribute__scope=ProductAttribute.Scope.PRODUCT,
            ).values_list("id", flat=True)
        )

        if not required_attr_ids:
            return

        existing_attr_ids = set(
            ProductSKUAttributeValue.objects.filter(
                product=self,
                product_sku__isnull=True,
                product_type_attribute_id__in=required_attr_ids,
            ).values_list("product_type_attribute_id", flat=True)
        )
        missing_attr_ids = required_attr_ids - existing_attr_ids

        if not missing_attr_ids:
            return

        ProductSKUAttributeValue.objects.bulk_create([
            ProductSKUAttributeValue(
                product=self,
                product_type_attribute_id=attr_id,
            )
            for attr_id in missing_attr_ids
        ])


class ProductSKU(ModelValidationMixin, models.Model):
    product = models.ForeignKey(
        to=Product,
        on_delete=models.CASCADE,
        related_name="skus",
        verbose_name=_("product"),
        help_text=_("The product this SKU belongs to."),
    )
    sku = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("SKU"),
        help_text=_("Unique stock keeping unit identifier for inventory tracking."),
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("title"),
        help_text=_("Optional SKU-specific title (e.g., '128GB Blue')."),
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("price"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("is active"),
        help_text=_("Whether this SKU is visible and available for sale."),
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name=_("is primary"),
        help_text=_("Marks this as the main SKU of the product."),
    )

    # Default manager
    objects = models.Manager()

    # Custom manager that only returns active SKUs whose
    # product and category are also active.
    active = ActiveProductSKUManager()

    class Meta:
        verbose_name = _("product SKU")
        verbose_name_plural = _("product SKUs")
        ordering = ["product", "sku"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "title"],
                name="unique_sku_title_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product.title} - {self.title or self.sku}"

    @transaction.atomic
    def save(self, *args, **kwargs):
        self._handle_is_primary()
        super().save(*args, **kwargs)
        self._create_required_attributes()

    # @cached_property
    # def is_available(self):
    #     stock = get_prefetched(self, 'prefetched_stocks', self.stocks.all())
    #     return stock[0].available > 0 if stock else False
    #
    # @cached_property
    # def primary_image_url(self):
    #     images = get_prefetched(
    #         obj=self,
    #         attr_name="prefetched_images",
    #         fallback_qs=self.images.all()
    #     )
    #     primary_image = next((image for image in images if image.is_primary), None)
    #     return primary_image.image_url if primary_image else ""

    @skip_if_missing_fields('product')
    def _validate_is_active(self):
        if self.is_active and not self.product.is_active:
            raise ValidationError({"is_active": _("Cannot activate SKU under inactive product.")})

    # ────────────────────────────────
    # Helpers
    # ────────────────────────────────
    def _handle_is_primary(self):

        qs = ProductSKU.objects.filter(product=self.product)

        if self.pk:
            qs = qs.exclude(pk=self.pk)

        if self.is_primary:
            qs.select_for_update().update(is_primary=False)

        elif not qs.filter(is_primary=True).exists():
            self.is_primary = True

    def _create_required_attributes(self):
        """
        Ensure all required VARIANT-scope attributes exist.
        These apply to the SKU itself, not its product.
        """
        required_attr_ids = set(
            ProductTypeAttribute.objects.filter(
                required=True,
                product_type=self.product.product_type,
                product_attribute__scope=ProductAttribute.Scope.VARIANT,
            ).values_list("id", flat=True)
        )

        if not required_attr_ids:
            return

        existing_attr_ids = set(
            ProductSKUAttributeValue.objects.filter(
                product=self.product,
                product_sku_id=self.pk,
                product_type_attribute_id__in=required_attr_ids,
            ).values_list("product_type_attribute_id", flat=True)
        )
        missing_attr_ids = required_attr_ids - existing_attr_ids

        if not missing_attr_ids:
            return

        ProductSKUAttributeValue.objects.bulk_create([
            ProductSKUAttributeValue(
                product=self.product,
                product_sku=self,
                product_type_attribute_id=attr_id,
            )
            for attr_id in missing_attr_ids
        ])


class ProductSKUAttributeValue(ModelValidationMixin, models.Model):
    """
    Represents the value of an attribute for either whole product or one of its SKUs.

    If `product_sku` is NULL, the value applies to the entire product (shared by all SKUs).
    If `product_sku` is set, the value applies only to that specific SKU.
    """

    product = models.ForeignKey(
        to=Product,
        on_delete=models.CASCADE,
        related_name="attribute_values",
        verbose_name=_("product"),
    )

    product_sku = models.ForeignKey(
        to=ProductSKU,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="attribute_values",
        verbose_name=_("SKU"),
    )

    product_type_attribute = models.ForeignKey(
        to=ProductTypeAttribute,
        on_delete=models.PROTECT,
        verbose_name=_("type attribute"),
    )

    value = models.ForeignKey(
        to=ProductAttributeOption,
        null=True,
        on_delete=models.PROTECT,
        verbose_name=_("attribute option"),
    )

    class Meta:
        verbose_name = _("product or SKU attribute value")
        verbose_name_plural = _("product and SKU attribute values")
        constraints = [
            models.UniqueConstraint(
                fields=["product", "product_sku", "product_type_attribute"],
                name="unique_product_sku_type_attribute",
            )
        ]

    @property
    def is_sku_level(self):
        """Returns True if this value is tied to a specific SKU."""
        return self.product_sku_id is not None

    def __str__(self):
        return _(
            "%(attribute)s: %(value)s (%(scope)s)"
        ) % {
            "attribute": self.product_type_attribute.product_attribute.title,
            "value": self.value.value if self.value else "",
            "scope": f"Sku: {self.product_sku.sku}" if self.product_sku else _("Product-wide"),
        }

    @skip_if_missing_fields('product_sku')
    def _validate_sku_belongs_to_product(self):
        """
        Ensures that the selected SKU actually belongs to the same product.
        """
        if self.product_sku and self.product_sku.product_id != self.product_id:
            raise ValidationError(
                {"product_sku": _("The selected sku does not belong to this product.")}
            )

    @skip_if_missing_fields('product_type_attribute', 'product')
    def _validate_attribute_belongs_to_product_type(self):
        """
        Ensures that the chosen type attribute is valid for this product's type.
        """
        if self.product_type_attribute.product_type_id != self.product.product_type_id:
            raise ValidationError(
                {"product_type_attribute": _("This attribute does not belong to the product type.")}
            )

    @skip_if_missing_fields('value', 'product_type_attribute')
    def _validate_attribute_value_belongs_to_attribute(self):
        """
        Ensures that the chosen value belongs to the correct attribute.
        """
        if self.value.product_attribute_id != self.product_type_attribute.product_attribute_id:
            raise ValidationError({"value": _("The selected option does not belong to the associated attribute.")})

    @skip_if_missing_fields('product_type_attribute')
    def _validate_scope_matches_sku_usage(self):
        attr_scope = self.product_type_attribute.product_attribute.scope
        if self.product_sku_id and attr_scope == ProductAttribute.Scope.PRODUCT:
            raise ValidationError({
                "product_type_attribute": _("Product-level attributes cannot be assigned to SKUs.")
            })
        if not self.product_sku_id and attr_scope == ProductAttribute.Scope.VARIANT:
            raise ValidationError({
                "product_type_attribute": _("SKU-level attributes cannot be assigned to products.")
            })

    @skip_if_missing_fields('product_type_attribute')
    def _validate_unique_attribute(self):

        qs = self.__class__.objects.filter(
            product_type_attribute_id=self.product_type_attribute_id,
            product_id=self.product_id
        )

        if self.product_sku_id:
            qs = qs.filter(product_sku_id=self.product_sku_id)

        if self.pk:
            qs = qs.exclude(pk=self.pk)

        if qs.exists():
            if self.product_sku_id:
                msg = _("This attribute already exists for this product SKU.")
            else:
                msg = _("This attribute already exists for this product.")

            raise ValidationError({'product_type_attribute': msg})


class ProductImage(ModelValidationMixin, models.Model):
    product_sku = models.ForeignKey(
        to=ProductSKU,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("SKU"),
    )
    image = models.ImageField(
        upload_to="products/images/",
        verbose_name=_("image"),
    )
    alt_text = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("alt text"),
        help_text=_("Descriptive text for accessibility and SEO."),
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name=_("is primary"),
        help_text=_("Mark as the main display image for this SKU"),
    )
    position = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("display order"),
        help_text=_("Smaller numbers appear first."),
    )

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return f"{self.product_sku.title}"

    @transaction.atomic
    def save(self, *args, **kwargs):
        self._handle_is_primary()
        super().save(*args, **kwargs)

    @skip_if_missing_fields("product")
    def _validate_unique_position(self):
        qs = ProductImage.objects.filter(product_sku=self.product_sku, position=self.position)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError({"position": _("This display order position is already used for another image.")})

    def _handle_is_primary(self):
        """
        Ensures that only one image is marked as primary per SKU
        """
        qs = ProductImage.objects.filter(product_sku=self.product_sku)

        if self.pk:
            qs = qs.exclude(pk=self.pk)

        if self.is_primary:
            qs.select_for_update().update(is_primary=False)
        else:
            if not qs.filter(is_primary=True).exists():
                self.is_primary = True


class ProductStock(ModelValidationMixin, models.Model):
    product_sku = models.ForeignKey(
        to=ProductSKU,
        on_delete=models.CASCADE,
        related_name="stocks",
        verbose_name=_("SKU"),
    )
    quantity = models.PositiveIntegerField(
        default=0,
        verbose_name=_("quantity"),
    )
    reserved = models.PositiveIntegerField(
        default=0,
        verbose_name=_("reserved"),
    )

    def __str__(self):
        return self.product_sku.title

    # ───────────────────────────────
    # Derived property
    # ───────────────────────────────
    @property
    def available(self) -> int:
        """Return available (not reserved) stock."""
        return max(0, self.quantity - self.reserved)

    # ───────────────────────────────
    # Stock operations
    # ───────────────────────────────
    def reserve(self, qty: int):
        """Reserve stock (for pending orders)."""
        if qty > self.available:
            raise ValidationError(_("Not enough available stock to reserve."))
        self.reserved += qty
        self.save(update_fields=["reserved"])

    def release(self, qty: int):
        """Release reserved stock (e.g., cancelled order)."""
        self.reserved = max(0, self.reserved - qty)
        self.save(update_fields=["reserved"])

    def decrease(self, qty: int):
        """Reduce total quantity after successful sale."""
        if qty > self.quantity:
            raise ValidationError(_("Cannot decrease more than available quantity."))
        self.quantity -= qty
        self.reserved = max(0, self.reserved - qty)
        self.save(update_fields=["quantity", "reserved"])

    def increase(self, qty: int):
        """Increase total quantity (restock)."""
        self.quantity += qty
        self.save(update_fields=["quantity"])

    # ───────────────────────────────
    # Validations
    # ───────────────────────────────

    def _validate_reserved(self):
        """Ensure reserved ≤ total quantity."""
        if self.reserved > self.quantity:
            raise ValidationError({"reserved": _("Reserved quantity cannot exceed total quantity.")})

    @skip_if_missing_fields("product")
    def _validate_unique_stock_per_product(self):
        qs = self.__class__.objects.filter(product_sku=self.product_sku)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(_("Stock entry for this SKU already exists."))
