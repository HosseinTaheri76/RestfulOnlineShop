from django.db.models.aggregates import Max, Min
from django.shortcuts import get_object_or_404

from rest_framework.response import Response
from rest_framework import generics, status
from rest_framework.filters import OrderingFilter, SearchFilter
from django_filters.rest_framework import DjangoFilterBackend

from . import models, queries, pagination, serializers, filters


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

class ProductListByCategoryView(generics.ListAPIView):
    """
    Returns a paginated list of active products under a category and its descendants.
    The response also includes:
      - Minimum and maximum product prices (for range sliders)
      - Filterable attributes and their options (for UI filters)
    """
    _category_cache = None  # Cached resolved category instance
    category_url_kwarg = "product_category_slug"
    serializer_class = serializers.ProductListSerializer
    pagination_class = pagination.ProductListPagination
    filterset_class = filters.ProductFilter
    filter_backends = [
        filters.ProductAttributeFilterBackend,
        DjangoFilterBackend,
    ]

    # --- Helpers -------------------------------------------------------------

    def get_category(self) -> models.ProductCategory:
        """Fetch and cache the category by slug."""
        if self._category_cache is None:
            slug = self.kwargs.get(self.category_url_kwarg)
            self._category_cache = get_object_or_404(
                models.ProductCategory.active.all(), slug=slug
            )
        return self._category_cache

    def get_queryset(self):
        """Return products belonging to the category (and its descendants)."""
        category = self.get_category()
        return queries.get_products_by_category(category)

    # --- Main list method ----------------------------------------------------

    def list(self, request, *args, **kwargs):
        category = self.get_category()

        # Apply all filter backends
        queryset = self.filter_queryset(self.get_queryset())

        # Compute min/max price efficiently
        price_range = queryset.aggregate(
            min_price=Min("effective_price"),
            max_price=Max("effective_price"),
        )

        # Get filterable attributes (cached / prefetched query)
        attribute_options = queries.get_attribute_options_by_category(category)
        filter_data = serializers.ProductAttributeSerializer(attribute_options, many=True).data

        # Paginate product results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            product_data = self.paginator.get_paginated_data(serializer.data)
        else:
            serializer = self.get_serializer(queryset, many=True)
            product_data = serializer.data

        # Build structured response
        response_data = {
            "min_price": price_range["min_price"],
            "max_price": price_range["max_price"],
            "filters": filter_data,
            "products": product_data,
        }

        return Response(response_data)


class ProductDetailView(generics.RetrieveAPIView):
    """
    Returns detailed information about a single product, including
    - Variants and their stocks/images
    - Attribute values (if `prefetch_attribute_values=True`)
    """
    lookup_field = "slug"
    lookup_url_kwarg = "product_slug"
    serializer_class = serializers.ProductDetailSerializer
    queryset = queries.get_products(prefetch_attribute_values=True)


class ProductCompareView(generics.GenericAPIView):
    serializer_class = serializers.ProductCompareSerializer

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
