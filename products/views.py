from rest_framework.viewsets import ReadOnlyModelViewSet

from . import queries
from . import serializers


class CategoryViewSet(ReadOnlyModelViewSet):
    serializer_class = serializers.ProductCategorySerializer

    def get_queryset(self):
        queryset = queries.get_categories()
        if self.action == 'list':
            return queryset.filter(parent__isnull=True)
        return queryset


class ProductViewSet(ReadOnlyModelViewSet):



    def get_serializer_class(self):
        if self.action == 'list':
            return serializers.ProductListSerializer
        return serializers.ProductDetailSerializer

    def get_queryset(self):
        return queries.get_products(prefetch_attribute_values=self.action == 'retrieve')
