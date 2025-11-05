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

from utils.models.helpers import get_prefetched
from utils.models.validation import ModelValidationMixin, skip_if_missing_fields


class ActiveProductCategoryManager(TreeManager):
    """
        Custom manager for the ProductCategory model that returns only *active* categories.

        This manager enforces a storefront-level visibility rule by excluding
        categories that are either:
          • Inactive themselves (`is_active=False`), or

        By using this manager, developers can safely query for categories that should
        be visible to customers without having to remember filtering conditions.
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class ActiveProductManager(models.Manager):
    """
    Custom manager for the Product model that returns only *active* products.

    This manager enforces a storefront-level visibility rule by excluding
    products that are either:

      • Inactive themselves (`is_active=False`), or
      • Belong to an inactive category (`product_category__is_active=False`).

    By using this manager, developers can safely query for products that should
    be visible to customers without having to remember filtering conditions.
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True, product_category__is_active=True)


class ActiveProductVariantManager(models.Manager):
    """
    Custom manager for the ProductVariant model that returns only *active* product-variants.

    This manager enforces a storefront-level visibility rule by excluding
    product variants that are either:

      • Inactive themselves (`is_active=False`), or
      • Belong to an inactive product (`product__is_active=False`).
      • Belong to an inactive category (`product__product_category__is_active=False`).

    By using this manager, developers can safely query for products that should
    be visible to customers without having to remember filtering conditions.
    """

    def get_queryset(self):
        return super().get_queryset().filter(
            is_active=True,
            product__is_active=True,
            product__product_category__is_active=True
        )


class ProductCategory(ModelValidationMixin, MPTTModel):
    """
    MPTT-backed product category with:
      - maximum tree depth enforced (levels 0..2 allowed)
      - activation propagation (up & down) with bulk updates
      - deactivation of ancestors when they have no active descendants
    """

    # configuration
    MAX_LEVEL = 2  # allowed levels: 0, 1, 2

    parent = TreeForeignKey(
        to="self",
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("parent"),
        on_delete=models.SET_NULL,
        limit_choices_to=Q(level__lt=MAX_LEVEL),
    )
    title = models.CharField(
        unique=True,
        max_length=255,
        verbose_name=_("title")
    )
    slug = models.SlugField(
        blank=True,
        unique=True,
        allow_unicode=True,
        verbose_name=_("slug")
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
    active = ActiveProductCategoryManager()
    # tracker to detect changes to parent and is_active
    _tracker = FieldTracker(fields=["parent_id", "is_active"])

    class MPTTMeta:
        order_insertion_by = ["title"]

    class Meta:
        verbose_name = _("Product category")
        verbose_name_plural = _("Product categories")
        constraints = [
            models.CheckConstraint(
                name="category_depth_less_than_equal_3", check=Q(level__lte=2)
            )
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def full_path(self) -> str:
        return " → ".join(self.get_ancestors(include_self=True).values_list("title", flat=True))

    # ----------------------------
    # Public model hooks
    # ----------------------------
    @transaction.atomic
    def save(self, *args, **kwargs) -> None:
        """
        On save:
          - ensure slug
          - validate (full_clean) so depth checks run before propagation
          - run activation propagation logic
        """
        self._set_slug()
        # handle activation/deactivation and re-parent cleanup (uses in-memory tracker)
        self._handle_activation()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse('products:product-list-by-category', kwargs={"product_category_slug": self.slug})

    @transaction.atomic
    def delete(self, *args, **kwargs) -> None:
        """
        When deleting an active node, we may need to clean up ancestors that
        no longer have active descendants.
        """
        # if this node is active and has a parent, ancestors might need deactivation
        if self.is_active and self.parent:
            # call on the node to compute and bulk-update ancestors
            self._deactivate_ancestors_if_has_no_active_descendants(self)
        super().delete(*args, **kwargs)

    # ----------------------------
    # Helpers: slug & depth
    # ----------------------------
    def _set_slug(self) -> None:
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)

    def _validate_depth(self) -> None:
        """
        Ensure creating/moving this node doesn't produce a tree deeper than MAX_LEVEL.
        Cases:
          - New node or leaf node: simply check parent's level.
          - Existing node with descendants: compute the farthest descendant and project new depth.
        """
        if not self.parent:
            return  # root nodes always OK

        error_msg = _("The category \"%(category)s\" cannot accept subcategories due to category depth limit.")

        # Case A: creating a new node or this node is a leaf — check parent level only
        if not self.pk or self.is_leaf_node():
            if self.parent.level >= self.MAX_LEVEL:
                raise ValidationError({"parent": error_msg % {"category": self.parent}})
            return

        # Case B: moving an existing node that has descendants
        # get maximum descendant level; if None fallback to this.level
        max_descendant_level = self.get_descendants().aggregate(max_level=Max("level"))["max_level"] or self.level

        # number of levels below this node's level (distance to the farthest descendant)
        distance_to_farthest = max_descendant_level - self.level

        # resulting deepest level when placed under new parent:
        resulting_deepest = self.parent.level + distance_to_farthest + 1

        if resulting_deepest > self.MAX_LEVEL:
            raise ValidationError({"parent": error_msg % {"category": self.parent}})

    def _validate_categories_with_products_cannot_accept_subcategories(self):
        """
        Ensure that a category that already has products cannot become
        a parent of another category. This maintains a clean category tree
        where leaf categories hold products, and parent categories only
        organize subcategories.
        """
        if self.parent and self.parent.products.exists():
            raise ValidationError(_("A category that contains products cannot have subcategories."))

    # ----------------------------
    # Helpers: activation propagation
    # ----------------------------
    @staticmethod
    def _deactivate_ancestors_if_has_no_active_descendants(node: "ProductCategory") -> None:
        """
        Walk ancestors from the nearest parent up to root and mark as inactive where they
        have no other active children. Implemented in-memory then bulk-updated to
        avoid many small queries/updates.

        Algorithm:
          - get ancestors ordered from nearest to root (reverse of get_ancestors())
          - keep a set `still_active_ids` of active nodes that should remain active
            (initially includes all active nodes in DB except those we will deactivate)
          - iterate ancestors; if an ancestor has no active child outside the
            already-deactivated set, mark it as to-be-deactivated
          - bulk update all deactivated nodes in one query
        """
        # load ancestors closest-first (nearest parent -> root)
        ancestors = list(node.get_ancestors().prefetch_related("children").all())

        # `to_deactivate` will collect pks we decide should be deactivated
        to_deactivate: Set[int] = set()
        # include the node itself as an already "deactivated" candidate
        to_deactivate.add(node.pk)

        # We'll check each ancestor's direct children; if none active outside to_deactivate, mark it
        for anc in reversed(ancestors):
            children = list(anc.children.all())
            # if there exists any active child not in to_deactivate, keep ancestor active
            has_active_child_outside = any(
                (child.is_active and child.pk not in to_deactivate) for child in children
            )
            if not has_active_child_outside:
                to_deactivate.add(anc.pk)

        if to_deactivate:
            ProductCategory.objects.filter(pk__in=to_deactivate).update(is_active=False)

    def _handle_activation(self) -> None:
        """
        Propagate activation/deactivation and fix up branches on parent changes.

        Behavior:
          - CREATE: if created as active and has parent -> activate ancestors
          - UPDATE (is_active toggled):
                * activated -> activate family (ancestors + descendants)
                * deactivated -> deactivate descendants and then deactivate ancestors that lost all active children
          - MOVE (parent changed):
                * if active and new parent -> ensure new ancestors (including parent) are active
                * for previous parent branch, recompute ancestors that may need deactivation
        """
        is_update = bool(self.pk)
        parent_changed = self._tracker.has_changed("parent_id")
        is_active_changed = self._tracker.has_changed("is_active")
        prev_parent_id: Optional[int] = self._tracker.previous("parent_id") if is_update else None

        # --- CREATE ---
        if not is_update:
            if self.is_active and self.parent:
                # activate parent and all its ancestors
                self.parent.get_ancestors(include_self=True).update(is_active=True)
            return

        # --- is_active toggled on existing node ---
        if is_active_changed:
            if self.is_active:
                # activate whole family (node + ancestors + descendants)
                self.get_family().update(is_active=True)
            else:
                # deactivate descendants (including self) and then cleanup ancestors
                self.get_descendants().update(is_active=False)
                self._deactivate_ancestors_if_has_no_active_descendants(self)

        # --- parent changed (re-parenting) ---
        if parent_changed:
            # if the node is active, ensure new parent branch is active
            if self.is_active and self.parent:
                self.parent.get_ancestors(include_self=True).update(is_active=True)

            # the previous parent branch may have lost its only active child -> cleanup
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

    _tracker = FieldTracker(fields=["has_variants", ])

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

    class Meta:
        verbose_name = _("Product Type")
        verbose_name_plural = _("Product Types")
        ordering = ["title"]

    def __str__(self):
        return self.title


class ProductBrand(models.Model):
    title = models.CharField(
        max_length=128,
        unique=True,
        verbose_name=_("title"),
    )
    slug = models.SlugField(
        max_length=128,
        allow_unicode=True,
        unique=True,
        blank=True,
        verbose_name=_("slug"),
    )

    class Meta:
        verbose_name = _("Brand")
        verbose_name_plural = _("Brands")

    def __str__(self):
        return self.title

    def _set_slug(self) -> None:
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)

    def save(self, *args, **kwargs):
        self._set_slug()
        super().save(*args, **kwargs)


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


class ProductAttributeOption(models.Model):
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


class Product(ModelValidationMixin, models.Model):
    """
    Represents a sellable product in the catalog.

    A product can either:
      - Be a standalone item with no variants (price stored directly here), or
      - Have variants (e.g., different sizes, colors, or configurations),
        in which case pricing and stock are defined at the variant level.

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
    sku = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        verbose_name=_("SKU"),
        help_text=_(
            "Stock Keeping Unit — required for products without variants. "
            "Leave blank if this product has variants; each variant will define its own SKU."
        ),
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        blank=True,
        allow_unicode=True,
        verbose_name=_("slug"),
        help_text=_("Unique identifier used in URLs. Auto-generated from title if left blank."),
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("price"),
        help_text=_(
            "Set a base price only if this product has no variants. "
            "For products with variants, leave this blank — "
            "each variant will define its own price."
        ),
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

    def _set_slug(self) -> None:
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)

    @transaction.atomic
    def save(self, *args, **kwargs):
        """Auto-generate slug from title if not provided."""
        self._set_slug()
        super().save(*args, **kwargs)
        self._create_required_attributes()

    def get_absolute_url(self) -> str:
        """Return absolute URL."""
        return reverse('products:product-detail', kwargs={'product_slug': self.slug})

    @cached_property
    def primary_variant(self):
        if self.product_type.has_variants:
            variants = get_prefetched(
                obj=self,
                attr_name="prefetched_variants",
                fallback_qs=self.variants(manager='active').all()
            )
            return next(filter(lambda variant: variant.is_primary, variants), None)
        return None

    @cached_property
    def is_available(self):
        """
        Determines if the product (or any of its variants, if applicable) has available stock.
        Uses prefetched data when available to avoid extra queries.
        """
        if self.product_type.has_variants:
            variants = get_prefetched(obj=self, attr_name="prefetched_variants", fallback_qs=self.variants.all())
            for variant in variants:
                if variant.is_available:
                    return True
            return False
        stocks = get_prefetched(obj=self, attr_name="prefetched_stocks", fallback_qs=self.stocks.all())
        return bool(stocks) and stocks[0].available > 0

    @cached_property
    def effective_price(self):
        """
        Returns the product's current sellable price.
        - For multi-variant products: returns the primary variant's price.
        - For single-variant products: returns the product's own price.
        Returns None if no price is applicable or the product is unavailable.
        """
        # Choose product or primary variant
        target = self.primary_variant if self.product_type.has_variants else self
        if not target:
            return None

        # Skip unavailable items early
        if not self.is_available:
            return None

        # Ensure price attribute exists and is valid
        return getattr(target, "price", None)

    @cached_property
    def primary_image_url(self):
        images = get_prefetched(
            obj=self,
            attr_name="prefetched_images",
            fallback_qs=self.images.all()
        )
        primary_image = next((image for image in images if image.is_primary), None)
        return primary_image.image.url if primary_image else ""

    @cached_property
    def thumbnail_image_url(self):
        """
        Returns the URL of the primary image for this product or its primary variant.
        Prefers product images; falls back to primary variant images if none exist.
        """
        product_primary_image = self.primary_image_url

        if product_primary_image:
            return product_primary_image
        if self.primary_variant:
            return self.primary_variant.primary_image_url
        return ""

    @skip_if_missing_fields("product_category")
    def _validate_category_is_leaf_node(self):
        if not self.product_category.is_leaf_node():
            raise ValidationError({'product_category': _('Product category must be a leaf node')})

    @skip_if_missing_fields("product_category")
    def _validate_is_active(self):
        if self.is_active and not self.product_category.is_active:
            raise ValidationError({"is_active": _("Cannot activate product under inactive category.")})

    @skip_if_missing_fields("product_type")
    def _validate_single_vs_multi_variant_fields(self):
        if self.product_type.has_variants:
            if self.price:
                raise ValidationError({'price': _("Price must be empty for products with variants.")})
            if self.sku:
                raise ValidationError({'sku': _("SKU must be empty for products with variants.")})
        else:
            if not self.price:
                raise ValidationError({'price': _("Price must be filled for single-variant products.")})
            if not self.sku:
                raise ValidationError({'sku': _("SKU must be filled for single-variant products.")})

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
                product_variant__isnull=True,
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


class ProductVariant(ModelValidationMixin, models.Model):
    """
    Represents a specific variation of a product (e.g., iPhone 16 128GB Blue vs iPhone 16 256GB Black).

    Each variant:
    - Belongs to a `Product`.
    - Has a unique SKU (Stock Keeping Unit).
    - Can optionally have its own display title.
    - Can be active/inactive independently, but activation is also dependent
      on the product and category being active.
    """

    product = models.ForeignKey(
        to=Product,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name=_("product"),
        help_text=_("The product this variant belongs to."),
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
        help_text=_("Optional variant-specific title (e.g., '128GB Blue')."),
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("price"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("is active"),
        help_text=_("Whether this variant is visible and available for sale."),
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name=_("is primary"),
        help_text=_("Marks this as the main variant of the product."),
    )

    # Default manager
    objects = models.Manager()

    # Custom manager that only returns active variants whose
    # product and category are also active.
    active = ActiveProductVariantManager()

    class Meta:
        verbose_name = _("product variant")
        verbose_name_plural = _("product variants")
        ordering = ["product", "sku"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "title"],
                name="unique_variant_title_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product.title} - {self.title or self.sku}"

    @transaction.atomic
    def save(self, *args, **kwargs):
        self._handle_is_primary()
        super().save(*args, **kwargs)
        self._create_required_attributes()

    @cached_property
    def is_available(self):
        stock = getattr(self, 'prefetched_stocks', [])
        return stock[0].available > 0 if stock else False

    @cached_property
    def primary_image_url(self):
        images = get_prefetched(
            obj=self,
            attr_name="prefetched_images",
            fallback_qs=self.images.all()
        )
        primary_image = next((image for image in images if image.is_primary), None)
        return primary_image.image_url if primary_image else ""

    # ────────────────────────────────
    # Validations
    # ────────────────────────────────
    @skip_if_missing_fields('product')
    def _validate_product_type_is_multi_variant(self):
        if not self.product.product_type.has_variants:
            raise ValidationError(_("This product cannot have variants."))

    @skip_if_missing_fields('product')
    def _validate_is_active(self):
        if self.is_active and not self.product.is_active:
            raise ValidationError({"is_active": _("Cannot activate variant under inactive product.")})

    # ────────────────────────────────
    # Helpers
    # ────────────────────────────────
    def _handle_is_primary(self):
        if not self.product.product_type.has_variants:
            return

        qs = ProductVariant.objects.filter(product=self.product)

        if self.pk:
            qs = qs.exclude(pk=self.pk)

        if self.is_primary:
            qs.select_for_update().update(is_primary=False)

        elif not qs.filter(is_primary=True).exists():
            self.is_primary = True

    def _create_required_attributes(self):
        """
        Ensure all required VARIANT-scope attributes exist.
        These apply to the variant itself, not its product.
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
                product_variant_id=self.pk,
                product_type_attribute_id__in=required_attr_ids,
            ).values_list("product_type_attribute_id", flat=True)
        )
        missing_attr_ids = required_attr_ids - existing_attr_ids

        if not missing_attr_ids:
            return

        ProductSKUAttributeValue.objects.bulk_create([
            ProductSKUAttributeValue(
                product=self.product,
                product_variant=self,
                product_type_attribute_id=attr_id,
            )
            for attr_id in missing_attr_ids
        ])


class ProductSKUAttributeValue(ModelValidationMixin, models.Model):
    """
    Represents the value of an attribute for either a product or one of its variants.

    If `product_variant` is NULL, the value applies to the entire product (shared by all variants).
    If `product_variant` is set, the value applies only to that specific variant.
    """

    product = models.ForeignKey(
        to=Product,
        on_delete=models.CASCADE,
        related_name="attribute_values",
        verbose_name=_("product"),
    )

    product_variant = models.ForeignKey(
        to=ProductVariant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="attribute_values",
        verbose_name=_("variant"),
    )

    product_type_attribute = models.ForeignKey(
        to=ProductTypeAttribute,
        on_delete=models.CASCADE,
        verbose_name=_("type attribute"),
    )

    value = models.ForeignKey(
        to=ProductAttributeOption,
        null=True,
        on_delete=models.CASCADE,
        verbose_name=_("attribute option"),
    )

    class Meta:
        verbose_name = _("product or variant attribute value")
        verbose_name_plural = _("product and variant attribute values")
        constraints = [
            models.UniqueConstraint(
                fields=["product", "product_variant", "product_type_attribute"],
                name="unique_product_variant_type_attribute",
            )
        ]

    @property
    def is_variant_level(self):
        """Returns True if this value is tied to a specific variant."""
        return self.product_variant_id is not None

    def __str__(self):
        return _(
            "%(attribute)s: %(value)s (%(scope)s)"
        ) % {
            "attribute": self.product_type_attribute.product_attribute.title,
            "value": self.value.value if self.value else "",
            "scope": f"Variant: {self.product_variant.sku}" if self.product_variant else _("Product-wide"),
        }

    @skip_if_missing_fields('product_variant')
    def _validate_variant_belongs_to_product(self):
        """
        Ensures that the selected variant actually belongs to the same product.
        """
        if self.product_variant and self.product_variant.product_id != self.product_id:
            raise ValidationError(
                {"product_variant": _("The selected variant does not belong to this product.")}
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
    def _validate_scope_matches_variant_usage(self):
        attr_scope = self.product_type_attribute.product_attribute.scope
        if self.product_variant_id and attr_scope == ProductAttribute.Scope.PRODUCT:
            raise ValidationError({
                "product_type_attribute": _("Product-level attributes cannot be assigned to variants.")
            })
        if not self.product_variant_id and attr_scope == ProductAttribute.Scope.VARIANT:
            raise ValidationError({
                "product_type_attribute": _("Variant-level attributes cannot be assigned to products.")
            })

    @skip_if_missing_fields('product_type_attribute')
    def _validate_unique_attribute(self):

        qs = self.__class__.objects.filter(
            product_type_attribute_id=self.product_type_attribute_id,
            product_id=self.product_id
        )

        if self.product_variant_id:
            qs = qs.filter(product_variant_id=self.product_variant_id)

        if self.pk:
            qs = qs.exclude(pk=self.pk)

        if qs.exists():
            if self.product_variant_id:
                msg = _("This attribute already exists for this product variant.")
            else:
                msg = _("This attribute already exists for this product.")

            raise ValidationError({'product_type_attribute': msg})


class ProductImage(ModelValidationMixin, models.Model):
    product = models.ForeignKey(
        to=Product,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("product"),
    )
    product_variant = models.ForeignKey(
        to=ProductVariant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("variant"),
        help_text=_("Optional. Attach this image to a specific variant (e.g., color photo)."),
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
        help_text=_("Mark as the main display image for this product or variant."),
    )
    position = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("display order"),
        help_text=_("Smaller numbers appear first."),
    )

    class Meta:
        ordering = ["position"]

    def __str__(self):
        scope = f"variant {self.product_variant.sku}" if self.product_variant else "product"
        return f"{self.product.title} ({scope})"

    @transaction.atomic
    def save(self, *args, **kwargs):
        self._handle_is_primary()
        super().save(*args, **kwargs)

    @skip_if_missing_fields("product")
    def _validate_variant_belongs_to_product(self):
        if self.product_variant and self.product_variant.product_id != self.product_id:
            raise ValidationError({"product_variant": _("Product variant must belong to the product.")})

    @skip_if_missing_fields("product", "product_variant")
    def _validate_variant_usage(self):
        if self.product_variant and not self.product.product_type.has_variants:
            raise ValidationError({
                "product_variant": _(
                    "This product type does not support "
                    "variants, so images cannot be variant-specific."
                )
            })

    @skip_if_missing_fields("product")
    def _validate_unique_position(self):
        qs = ProductImage.objects.filter(product=self.product, position=self.position)
        if self.product_variant_id:
            qs = qs.filter(product_variant=self.product_variant)
        else:
            qs = qs.filter(product_variant__isnull=True)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError({"position": _("This display order position is already used for another image.")})

    def _handle_is_primary(self):
        """
        Ensures that only one image is marked as primary per product or variant.
        """
        qs = ProductImage.objects.filter(product=self.product)

        if self.product_variant_id:
            qs = qs.filter(product_variant=self.product_variant)
        else:
            qs = qs.filter(product_variant__isnull=True)

        if self.pk:
            qs = qs.exclude(pk=self.pk)

        if self.is_primary:
            qs.select_for_update().update(is_primary=False)
        else:
            if not qs.filter(is_primary=True).exists():
                self.is_primary = True


class ProductStock(ModelValidationMixin, models.Model):
    product = models.ForeignKey(
        to=Product,
        on_delete=models.CASCADE,
        related_name="stocks",
        verbose_name=_("product"),
    )
    product_variant = models.ForeignKey(
        to=ProductVariant,
        on_delete=models.CASCADE,
        related_name="stocks",
        null=True,
        blank=True,
        verbose_name=_("variant / SKU"),
        help_text=_("Optional. Leave empty for products without variants."),
    )
    quantity = models.PositiveIntegerField(
        default=0,
        verbose_name=_("quantity"),
    )
    reserved = models.PositiveIntegerField(
        default=0,
        verbose_name=_("reserved"),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "product_variant"],
                name="unique_stock_per_product_or_variant",
            ),
        ]

    def __str__(self):
        if self.product_variant:
            return f"{self.product.title} - {self.product_variant.sku}"
        return f"{self.product.title}"

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
    @skip_if_missing_fields("product_variant", "product")
    def _validate_variant_belongs_to_product(self):
        """Ensure the variant belongs to the same product."""
        if self.product_variant and self.product_variant.product_id != self.product_id:
            raise ValidationError({"product_variant": _("Variant must belong to the product.")})

    def _validate_reserved(self):
        """Ensure reserved ≤ total quantity."""
        if self.reserved > self.quantity:
            raise ValidationError({"reserved": _("Reserved quantity cannot exceed total quantity.")})

    @skip_if_missing_fields("product")
    def _validate_variant_usage(self):
        """
        Validate that:
        - Single-variant products should not have a variant-specific stock.
        - Multi-variant products must specify a variant.
        """
        product_has_variants = self.product.product_type.has_variants

        if product_has_variants and not self.product_variant:
            raise ValidationError(
                {"product_variant": _("Stock entry for multi-variant product must specify a variant.")}
            )

        if not product_has_variants and self.product_variant:
            raise ValidationError(
                {"product_variant": _("Stock entry for single-variant product must not specify a variant.")}
            )

    @skip_if_missing_fields("product")
    def _validate_unique_stock_per_product(self):
        qs = self.__class__.objects.filter(product=self.product)
        if self.product_variant:
            qs = qs.filter(product_variant=self.product_variant)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(_("Stock entry for product/variant already exists."))
