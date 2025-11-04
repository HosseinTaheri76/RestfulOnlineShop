from django.db.models import Q
from django.db.models.fields import IntegerField
from django.utils.translation import gettext_lazy as _
from django.db.models.expressions import ExpressionWrapper, F, OuterRef, Exists

import django_filters
from rest_framework.filters import BaseFilterBackend

from .models import ProductAttribute, Product, ProductStock

class ProductAttributeFilterBackend(BaseFilterBackend):
    """
    Filter products by multiple attributes and their selected options.
    Supports both product and variant attribute values.
    """

    @staticmethod
    def clean_attribute_value(key: str, value: list):
        """
        Parse a query parameter like 'attr12=1' into (12, [1]).

        Returns (attribute_id, option_ids) if valid, otherwise (None, None).
        """
        if not (isinstance(key, str) and key.startswith("attr") and isinstance(value, list)):
            return None, None

        # Extract numeric part from a key
        num_part = key.replace("attr", "").strip()
        if not num_part.isdigit():
            return None, None

        attribute_id = int(num_part)

        # Extract valid option IDs
        option_ids = [int(v) for v in value if isinstance(v, (str, int)) and str(v).isdigit()]

        if not option_ids:
            return None, None

        return attribute_id, option_ids

    def filter_queryset(self, request, queryset, view):
        """
        Filter products by multiple attribute-value groups, allowing multiple attributes
        each with multiple possible values (OR within group, AND across groups).
        """
        attr_filters = []

        # Parse all "attr{id}=" parameters
        for key, value in request.query_params.lists():
            attr_id, option_ids = self.clean_attribute_value(key, value)
            if attr_id and option_ids:
                attr_filters.append((attr_id, option_ids))

        if not attr_filters:
            return queryset

        filterable_attributes = ProductAttribute.objects.filter(
            filterable=True,
            id__in=[attr_id for attr_id, _ in attr_filters]
        ).values_list("id", flat=True).distinct()

        # Apply filters sequentially (intersection logic)
        for attr_id, option_ids in attr_filters:

            if attr_id not in filterable_attributes:
                continue

            queryset = queryset.filter(
                Q(
                    attribute_values__product_type_attribute__product_attribute_id=attr_id,
                    attribute_values__value_id__in=option_ids
                )
                |
                Q(
                    variants__attribute_values__product_type_attribute__product_attribute_id=attr_id,
                    variants__attribute_values__value_id__in=option_ids
                )
            )

        return queryset.distinct()



class ProductFilter(django_filters.FilterSet):
    """
    Filters products by:
      - price range (min_price, max_price)
      - availability (based on stock availability)
      - title (case-insensitive contains)
      - brand (exact or multiple IDs)
    """

    min_price = django_filters.NumberFilter(
        field_name="effective_price",
        lookup_expr="gte",
        label=_("Minimum price"),
    )
    max_price = django_filters.NumberFilter(
        field_name="effective_price",
        lookup_expr="lte",
        label=_("Maximum price"),
    )

    is_available = django_filters.BooleanFilter(
        method="filter_is_available",
        label=_("Is available"),
    )

    title = django_filters.CharFilter(
        field_name="title",
        lookup_expr="icontains",
        label=_("Title contains"),
    )

    product_brand = django_filters.BaseCSVFilter(
        field_name="product_brand_id",
        lookup_expr="in",
        label=_("Brand IDs"),
    )

    class Meta:
        model = Product
        fields = ["min_price", "max_price", "is_available", "title", "product_brand"]

    # ────────────────────────────────
    # Custom Filters
    # ────────────────────────────────
    @staticmethod
    def filter_is_available(queryset, name, value):
        """
        Annotates queryset with 'is_available' based on stock availability.
        A product is available if:
          - Any of its own ProductStock has (quantity - reserved) > 0, OR
          - Any of its variant stocks does.
        """

        # Expression: available_quantity = quantity - reserved
        available_expr = ExpressionWrapper(
            F("quantity") - F("reserved"),
            output_field=IntegerField()
        )

        # Subquery to detect availability across product or its variants
        stock_subquery = ProductStock.objects.annotate(
            available_quantity=available_expr
        ).filter(
            Q(product=OuterRef("pk")) | Q(product_variant__product=OuterRef("pk")),
            available_quantity__gt=0,
        )

        # Annotate availability once
        queryset = queryset.annotate(is_available=Exists(stock_subquery))

        # Apply the boolean filter
        if value is True:
            return queryset.filter(is_available=True)
        elif value is False:
            return queryset.filter(is_available=False)
        return queryset
