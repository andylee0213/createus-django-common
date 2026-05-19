# filename: createus_common/billing/models/payments.py

from django.db import models

from createus_common.models import TimeStampedModel
from createus_common.billing.choices import (
    BillingCurrency,
    PaymentMethodType,
    PaymentProvider,
    PaymentStatus,
)


class AbstractPaymentTransaction(TimeStampedModel):
    """
    A single payment attempt.  Project apps subclass this to add FKs to
    their user model and any domain-specific order objects.

    order_id is set by the backend before the payment window opens and
    must be stored so it can be verified during the confirm callback.
    """

    order_id = models.CharField(max_length=64, unique=True, db_index=True)
    # Assigned by the provider after successful authentication
    payment_key = models.CharField(max_length=200, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.IntegerField(
        choices=BillingCurrency.choices, default=BillingCurrency.KRW
    )
    status = models.IntegerField(
        choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    provider = models.IntegerField(choices=PaymentProvider.choices)
    method_type = models.IntegerField(
        choices=PaymentMethodType.choices, null=True, blank=True
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    receipt_url = models.URLField(max_length=500, blank=True, default="")

    # Cancellation fields
    cancel_reason = models.TextField(blank=True, default="")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    # Full provider response stored for auditing and debugging
    raw_response = models.JSONField(null=True, blank=True)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return self.order_id
