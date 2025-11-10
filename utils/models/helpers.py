from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class SlugModelMixin(models.Model):
    generate_slug_from = 'title'

    slug = models.SlugField(
        blank=True,
        unique=True,
        allow_unicode=True,
        verbose_name=_("slug"),
        help_text=_("Unique identifier used in URLs. Auto-generated from title if left blank.")
    )

    def _set_slug(self):
        if not self.slug:
            self.slug = slugify(getattr(self, self.generate_slug_from), allow_unicode=True)

    def save(self, *args, **kwargs):
        self._set_slug()
        super().save(*args, **kwargs)

    class Meta:
        abstract = True


def get_prefetched(obj, attr_name, fallback_qs):
    """
    Return prefetched objects from `attr_name` if available,
    otherwise evaluate and return the given fallback queryset as a list.
    """
    items = getattr(obj, attr_name, None)
    if items is not None:
        return items
    return list(fallback_qs)
