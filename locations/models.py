from django.db import models
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from model_utils.tracker import FieldTracker


class Province(models.Model):
    title = models.CharField(_("title"), max_length=128, unique=True)
    is_active = models.BooleanField(_("active"), default=True)

    _tracker = FieldTracker(fields=["is_active", ])

    class Meta:
        verbose_name = _("province")
        verbose_name_plural = _("provinces")
        ordering = ("title",)

    def __str__(self):
        return self.title

    @transaction.atomic
    def save(self, *args, **kwargs):
        self._handle_activation()
        super().save(*args, **kwargs)

    def _handle_activation(self):
        if self.pk and self._tracker.has_changed("is_active"):
            self.cities.update(is_active=self.is_active)


class City(models.Model):
    province = models.ForeignKey(
        to=Province,
        on_delete=models.CASCADE,
        related_name="cities",
        verbose_name=_("province"),
    )
    title = models.CharField(_("title"), max_length=128)
    is_active = models.BooleanField(_("active"), default=True)

    _tracker = FieldTracker(fields=["is_active", ])

    class Meta:
        verbose_name = _("city")
        verbose_name_plural = _("cities")
        unique_together = (("province", "title"),)
        ordering = ("title",)

    def __str__(self):
        return f"{self.province.title} : {self.title}"

    @transaction.atomic
    def save(self, *args, **kwargs):
        self._handle_activation()
        super().save(*args, **kwargs)

    def _update_province_status(self, status: bool):
        Province.objects.filter(pk=self.province.pk).update(is_active=status)

    def _handle_activation(self):
        if self._tracker.has_changed("is_active"):
            if self.is_active:
                self._update_province_status(True)
            elif not self.province.cities.exclude(pk=self.pk).filter(is_active=True).exists():
                self._update_province_status(False)
