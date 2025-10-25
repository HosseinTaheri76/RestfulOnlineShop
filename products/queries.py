from django.db.models.query import Prefetch

from . import models


def get_categories():
    model = models.ProductCategory

    prefetched_descendants = Prefetch(
        lookup='children',
        to_attr='prefetched_children',
        queryset=(
            model.active.prefetch_related(
                Prefetch(
                    lookup='children',
                    to_attr='prefetched_children',
                    queryset=model.active.get_queryset(),
                )
            )
        )
    )

    return model.active.prefetch_related(prefetched_descendants)


def get_products(prefetch_attribute_values=False):
    product_model = models.Product
    product_image_model = models.ProductImage
    product_stock_model = models.ProductStock
    product_variant_model = models.ProductVariant
    product_sku_attribute_value_model = models.ProductSKUAttributeValue

    product_variant_prefetches = [
        Prefetch(lookup='stocks', to_attr='prefetched_stocks'),
        Prefetch(lookup='images', to_attr='prefetched_images')
    ]

    product_prefetches = [
        Prefetch(
            lookup='stocks',
            to_attr='prefetched_stocks',
            queryset=product_stock_model.objects.filter(product_variant__isnull=True)
        ),
        Prefetch(
            lookup='images',
            to_attr='prefetched_images',
            queryset=product_image_model.objects.filter(product_variant__isnull=True)
        )
    ]

    if prefetch_attribute_values:
        product_variant_prefetches.append(
            Prefetch(
                lookup='attribute_values',
                to_attr='prefetched_attribute_values',
                queryset=product_sku_attribute_value_model.objects.select_related('value__product_attribute')
            )
        )
        product_prefetches.append(
            Prefetch(
                lookup='attribute_values',
                to_attr='prefetched_attribute_values',
                queryset=(
                    product_sku_attribute_value_model.objects.
                    filter(product_variant__isnull=True).
                    select_related('value__product_attribute')
                )
            )
        )

    product_prefetches.append(
        Prefetch(
            lookup='variants',
            to_attr='prefetched_variants',
            queryset=product_variant_model.active.prefetch_related(*product_variant_prefetches)
        )
    )

    return (
        product_model.active.
        select_related('product_type', 'product_category').
        prefetch_related(*product_prefetches)
    )
