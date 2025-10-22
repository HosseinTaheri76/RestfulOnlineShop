from django.db.models.query import Prefetch

from rest_framework.viewsets import ReadOnlyModelViewSet

from . import models
from . import serializers


class CategoryViewSet(ReadOnlyModelViewSet):
    serializer_class = serializers.ProductCategorySerializer

    def get_queryset(self):
        queryset = models.ProductCategory.active.get_queryset()
        if self.action == 'list':
            queryset = queryset.filter(parent__isnull=True)
        return queryset.prefetch_related(
            Prefetch('children', queryset=models.ProductCategory.active.prefetch_related(
                Prefetch('children', queryset=models.ProductCategory.active.get_queryset())
            )),
        )

class ProductViewSet(ReadOnlyModelViewSet):
    def get_serializer_class(self):
        if self.action == 'list':
            return serializers.ProductListSerializer
        return serializers.ProductDetailSerializer

    def get_queryset(self):
        return (
            models.Product.active.get_queryset().
            select_related('product_category', 'product_type').
            prefetch_related(
                Prefetch(lookup='images'),
                Prefetch(lookup='stocks'),
                Prefetch(
                    lookup='attribute_values',
                    queryset=models.ProductSKUAttributeValue.objects.select_related('value__product_attribute')
                ),
                Prefetch(
                    lookup='variants',
                    queryset=models.ProductVariant.objects.prefetch_related(
                        Prefetch(lookup='images'),
                        Prefetch(lookup='stocks'),
                        Prefetch(
                            lookup='attribute_values',
                            queryset=models.ProductSKUAttributeValue.objects.select_related('value__product_attribute')
                        )
                    )
                )
            )
        )
