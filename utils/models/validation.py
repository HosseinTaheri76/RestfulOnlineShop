from functools import wraps

from django.core.exceptions import ValidationError


class ModelValidationMixin:
    """
    A reusable mixin for Django models that automatically discovers and runs all
    instance methods whose names start with `_validate`.

    Each `_validate_*` method should raise a `ValidationError` if validation fails.

    All collected errors are merged and raised together as a single ValidationError,
    allowing multiple issues to be reported at once instead of failing fast.

    Example:
        class Product(ModelValidationMixin, models.Model):
            price = models.DecimalField(...)
            stock = models.PositiveIntegerField(...)

            def _validate_price(self):
                if self.price is not None and self.price < 0:
                    raise ValidationError({'price': "Price must be positive."})
    """

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        # Run parent model validation first
        super().clean()

        errors = {}

        for attr_name in dir(self):
            # Skip non-validator methods and Django internals like _validate_force_insert
            if not attr_name.startswith("_validate") or attr_name.startswith("_validate_force_"):
                continue

            validator = getattr(self, attr_name)
            if callable(validator):
                try:
                    validator()
                except ValidationError as e:
                    if hasattr(e, "error_dict"):
                        # Merge dictionary-style errors (e.g. {'field': ['error']})
                        for field, msgs in e.message_dict.items():
                            errors.setdefault(field, []).extend(msgs)
                    elif hasattr(e, "error_list"):
                        # Collect general (non-field-specific) errors
                        errors.setdefault("__all__", []).extend(e.messages)
                    else:
                        errors.setdefault("__all__", []).append(str(e))

        if errors:
            raise ValidationError(errors)


def skip_if_missing_fields(*field_names):
    """
    Decorator to skip a validator method if any of the given fields are missing (None).
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            for field in field_names:
                # Use <field>_id to avoid fetching a related object
                if getattr(self, f"{field}_id", None) is None:
                    return None
            return func(self, *args, **kwargs)

        return wrapper

    return decorator
