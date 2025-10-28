"""
views.py

API views for categories, products, and product attributes.

These use DRF generic views with optimized querysets from `queries.py`
to ensure minimal database hits and clean separation of concerns.
"""

from django.shortcuts import get_object_or_404
from rest_framework import generics

from . import models, queries, pagination, serializers, filter_backends


# ───────────────────────────────────────────────
# Base mixins
# ───────────────────────────────────────────────

class CategoryContextMixin:
    """
    Mixin to retrieve the current category instance from URL kwargs.
    Used by all category-based views.
    """

    category_url_kwarg = "product_category_slug"

    def get_category(self) -> models.ProductCategory:
        """
        Resolve and cache the active category by slug.
        """
        if not hasattr(self, "_category_cache"):
            slug = self.kwargs[self.category_url_kwarg]
            self._category_cache = get_object_or_404(models.ProductCategory.active.all(), slug=slug)

        return self._category_cache


# ───────────────────────────────────────────────
# Category Views
# ───────────────────────────────────────────────

class CategoryListView(generics.ListAPIView):
    """
    Returns the full category tree (top-level + descendants)
    for display in navigation menus or category explorers.
    """
    queryset = queries.get_categories_for_tree_view()
    serializer_class = serializers.ProductCategorySerializer


# ───────────────────────────────────────────────
# Product Views
# ───────────────────────────────────────────────

class ProductListByCategoryView(CategoryContextMixin, generics.ListAPIView):
    """
    Returns a paginated list of products under a given category and its descendants.
    Includes stock, image, and variant prefetches for efficiency.
    """
    serializer_class = serializers.ProductListSerializer
    pagination_class = pagination.ProductListPagination
    filter_backends = [filter_backends.AttributeOptionFilterBackend, ]

    def get_queryset(self):
        category = self.get_category()
        return queries.get_products_by_category(category)


class ProductDetailView(generics.RetrieveAPIView):
    """
    Returns detailed information about a single product, including
    - Variants and their stocks/images
    - Attribute values (if `prefetch_attribute_values=True`)
    """
    lookup_field = "slug"
    lookup_url_kwarg = "product_slug"
    serializer_class = serializers.ProductDetailSerializer
    queryset = queries.get_product_queryset(prefetch_attribute_values=True)


# ───────────────────────────────────────────────
# Attribute Filter Views
# ───────────────────────────────────────────────

class ProductAttributeOptionListByCategoryView(CategoryContextMixin, generics.ListAPIView):
    """
    Returns all filterable attributes and their options for products
    under a given category. Used to build product filters on the frontend.
    """
    serializer_class = serializers.ProductAttributeSerializer

    def get_queryset(self):
        category = self.get_category()
        return queries.get_attribute_options_by_category(category)
