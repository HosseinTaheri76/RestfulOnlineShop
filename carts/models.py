from uuid import uuid4

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from products.models import ProductSKU

class Cart(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
        verbose_name=_('ID'),
    )
    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('User'),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created at'),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated at'),
    )

    def __str__(self):
        return str(self.id)


class CartItem(models.Model):
    cart = models.ForeignKey(
        to=Cart,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('Cart'),
    )
    sku = models.ForeignKey(
        to=ProductSKU,
        on_delete=models.PROTECT,
        related_name='cart_items',
        verbose_name=_('Product'),
    )
    quantity = models.PositiveIntegerField(
        default=1,
        verbose_name=_('Quantity'),
    )
    class Meta:
        unique_together = (('cart', 'sku'),)

