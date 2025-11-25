"""
queries.py

Centralized query helpers for products, categories, and attributes.

These functions are designed to:
- Optimize Django ORM performance using select_related and prefetch_related.
- Keep view logic clean and declarative.
- Minimize redundant database hits for related models (stocks, variants, images, attributes, etc.).
"""

from django.db.models import Prefetch, QuerySet, Case, When, OuterRef, Subquery, F, DecimalField
from django.db.models.aggregates import Max

from . import models
from .models import ProductStock

# ───────────────────────────────────────────────────────────────
# CATEGORIES
# ───────────────────────────────────────────────────────────────

def get_categories_for_tree_view() -> QuerySet:
    """
    Return a queryset of top-level active categories with their immediate
    and secondary-level children prefetched for tree view rendering.
    """
    Category = models.ProductCategory
    active = Category.active

    # Prefetch up to 2 levels of children for efficient category trees
    prefetched_children = Prefetch(
        lookup="children",
        to_attr="prefetched_children",
        queryset=active.prefetch_related(
            Prefetch(
                lookup="children",
                to_attr="prefetched_children",
                queryset=active.all(),
            )
        ),
    )

    return active.filter(parent__isnull=True).prefetch_related(prefetched_children)


# ───────────────────────────────────────────────────────────────
# PRODUCTS BY CATEGORY
# ───────────────────────────────────────────────────────────────

def get_products_by_category(product_category: models.ProductCategory) -> QuerySet:
    """
    Return all products under a given category (including descendants).

    Args:
        product_category (ProductCategory): The category instance.

    Returns:
        QuerySet[Product]: Active products belonging to this category tree.
    """
    category_ids = (
        product_category.get_descendants(include_self=True)
        .filter(is_active=True)
        .values_list("id", flat=True)
    )

    return get_products(prefetch_attribute_values=False).filter(product_category_id__in=category_ids)


# ───────────────────────────────────────────────────────────────
# ATTRIBUTE OPTIONS BY CATEGORY
# ───────────────────────────────────────────────────────────────

def get_attribute_options_by_category(product_category: models.ProductCategory) -> QuerySet:
    """
    Return all filterable ProductAttribute instances and their options
    related to the given product category and its descendants.

    Useful for displaying category-specific product filters (faceted search).

    Args:
        product_category (ProductCategory): The root category instance.

    Returns:
        QuerySet[ProductAttribute]: Filterable attributes with preloaded options.
    """
    # Get all active category IDs in this branch
    category_ids = (
        product_category.get_descendants(include_self=True)
        .filter(is_active=True)
        .values_list("id", flat=True)
    )

    # Get all product types linked to these categories
    product_type_ids = (
        models.ProductType.objects.filter(product_category_id__in=category_ids)
        .values_list("id", flat=True)
    )

    # Get attribute IDs associated with those product types
    attribute_ids = (
        models.ProductTypeAttribute.objects.filter(product_type_id__in=product_type_ids)
        .values_list("product_attribute_id", flat=True)
    )

    # Prefetch all related options (e.g., color, size) into `prefetched_options`
    option_prefetch = Prefetch(
        lookup="options",
        to_attr="prefetched_options",
        queryset=models.ProductAttributeOption.objects.all(),
    )

    # Return filterable attributes related to the current category's product types
    return (
        models.ProductAttribute.objects.filter(
            id__in=attribute_ids,
            filterable=True
        )
        .prefetch_related(option_prefetch)
        .distinct()
    )


def get_products(prefetch_attribute_values: bool = False):
    Product = models.Product
    ProductSKU = models.ProductSKU
    ProductSKUAttributeValue = models.ProductSKUAttributeValue

    product_prefetches = []

    sku_prefetches = [
        Prefetch('stocks', to_attr='prefetched_stocks'),
        Prefetch('images', to_attr='prefetched_images'),
    ]

    if prefetch_attribute_values:
        sku_prefetches.append(
            Prefetch(
                lookup='attribute_values',
                to_attr='prefetched_attribute_values',
                queryset=ProductSKUAttributeValue.objects.select_related(
                    "value__product_attribute",
                    "product_type_attribute__product_attribute"
                )
            )
        )
        product_prefetches.append(
            Prefetch(
                lookup="attribute_values",
                to_attr="prefetched_attribute_values",
                queryset=(
                    ProductSKUAttributeValue.objects.
                    filter(product_sku__isnull=True).
                    select_related(
                        "value__product_attribute",
                        "product_type_attribute__product_attribute"
                    )
                ),
            )
        )

    product_prefetches.append(
        Prefetch(
            lookup="skus",
            to_attr="prefetched_skus",
            queryset=ProductSKU.active.prefetch_related(*sku_prefetches),
        )
    )

    primary_sku_price = (
        ProductSKU.active
        .filter(product=OuterRef("pk"), is_primary=True)
        .values("price")[:1]
    )

    # Return optimized queryset
    return (
        Product.active
        .select_related("product_type", "product_category", "product_brand")
        .prefetch_related(*product_prefetches)
        .annotate(effective_price=Subquery(primary_sku_price),)
    )