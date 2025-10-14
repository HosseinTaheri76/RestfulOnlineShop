from typing import Optional, Set

from django.db import models, transaction
from django.db.models import Q
from django.db.models.aggregates import Max
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from model_utils import FieldTracker
from mptt.models import MPTTModel, TreeForeignKey


class ProductCategory(MPTTModel):
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

    def clean(self) -> None:
        """
        Validate tree depth rules prior to saving/moving.
        """
        self._validate_depth()

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
        ancestors = list(node.get_ancestors().prefetch_related("children").all())[::-1]

        # `to_deactivate` will collect pks we decide should be deactivated
        to_deactivate: Set[int] = set()
        # include the node itself as an already "deactivated" candidate
        to_deactivate.add(node.pk)

        # We'll check each ancestor's direct children; if none active outside to_deactivate, mark it
        for anc in ancestors:
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


class ProductType(models.Model):
    """
    Represents a product schema defining which attributes and variant logic apply to products.

    Examples:
        - "Smartphone" (has variants like different storage or colors)
        - "Laptop" (no variants)
        - "T-Shirt" (variants by color and size)
    """

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

    class Meta:
        verbose_name = _("Product Type")
        verbose_name_plural = _("Product Types")
        ordering = ["title"]

    def __str__(self):
        return self.title


class ProductAttribute(models.Model):
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

    class Meta:
        verbose_name = _("Product Attribute")
        verbose_name_plural = _("Product Attributes")
        ordering = ["title"]

    def __str__(self):
        return self.title


class ProductTypeAttribute(models.Model):
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
    def clean(self):
        """
        Performs validation to ensure:
        Variant-level attributes aren't used on non-variant product types.
        """
        self._validate_scope_compatibility()

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
