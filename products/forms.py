from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils.translation import gettext_lazy as _


class ProductSKUAttributeValueInlineFormSet(BaseInlineFormSet):
    """
    Inline formset for ProductSKUAttributeValue.

    Ensures that all required attributes (defined by the product's type)
    are filled in for either the Product or its SKU before saving.

    Validation is performed using in-memory form data,
    so it includes unsaved inlines and ignores deleted ones.
    """

    def clean(self):
        super().clean()

        parent_obj = self.instance

        if not parent_obj:
            return  # No parent object yet (likely during initial admin load)

        # ---------------------------
        # Determine the ProductType
        # ---------------------------
        # Works for both Product and ProductSKU contexts
        product_type = getattr(
            getattr(parent_obj, "product", None),
            "product_type",
            getattr(parent_obj, "product_type", None),
        )

        if not product_type:
            return  # Skip validation if a product type is not set yet

        # ---------------------------
        # Step 1: Get required TypeAttributes
        # ---------------------------
        required_type_attrs = product_type.type_attributes.filter(required=True)

        if not required_type_attrs.exists():
            return  # No required attributes, skip validation

        # ---------------------------
        # Step 2: Collect filled attributes from inline forms
        # ---------------------------
        filled_type_attr_ids = set()

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue  # Skip unvalidated forms (e.g., empty extra forms)

            if form.cleaned_data.get("DELETE", False):
                continue  # Ignore deleted forms

            type_attr = form.cleaned_data.get("product_type_attribute")
            value = form.cleaned_data.get("value")

            # Consider attribute filled if a non-empty value exists
            if type_attr and value not in (None, "", []):
                filled_type_attr_ids.add(type_attr.id)

        # ---------------------------
        # Step 3: Identify missing required attributes
        # ---------------------------
        missing_attrs = [
            ta.product_attribute.title
            for ta in required_type_attrs
            if ta.id not in filled_type_attr_ids
        ]

        # ---------------------------
        # Step 4: Raise a clean validation error
        # ---------------------------
        if missing_attrs:
            raise ValidationError(
                _("The following required attributes are missing: %(attrs)s"),
                params={"attrs": ", ".join(missing_attrs)},
            )
