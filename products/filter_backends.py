from django.db.models import Q
from rest_framework.filters import BaseFilterBackend


class AttributeOptionFilterBackend(BaseFilterBackend):
    """
    Filters products by selected ProductAttributeOption IDs.
    Example:attr-values=1,13,22
    """

    def filter_queryset(self, request, queryset, view):

        attr_options = request.query_params.get("attr-options")

        if not attr_options:
            return queryset

        try:
            option_ids = [int(v.strip()) for v in attr_options.split(",") if v.strip().isdigit()]

        except ValueError:
            return queryset

        if not option_ids:
            return queryset

        return queryset.filter(
            Q(attribute_values__value_id__in=option_ids) |
            Q(variants__attribute_values__value_id__in=option_ids)
        ).distinct()
