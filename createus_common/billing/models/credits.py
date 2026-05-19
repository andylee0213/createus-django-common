# filename: createus_common/billing/models/credits.py

from django.db import models

from createus_common.models import TimeStampedModel
from createus_common.billing.choices import CreditSourceType, CreditTransactionType


class AbstractUsageCreditBalance(TimeStampedModel):
    """
    Holds the current credit balance for a single subject (typically a user).

    Project apps must add:
        user = models.OneToOneField(settings.AUTH_USER_MODEL, ...)
    """

    balance = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return str(self.balance)


class AbstractUsageCreditHistory(TimeStampedModel):
    """
    Immutable ledger entry recording every credit change.

    Project apps must add:
        user = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
    """

    transaction_type = models.IntegerField(choices=CreditTransactionType.choices)
    source_type = models.IntegerField(choices=CreditSourceType.choices)
    # Positive for grants/refunds, negative for deductions/expirations
    amount = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    description = models.CharField(max_length=255, blank=True, default="")
    # Opaque reference linking this entry to an order, subscription, etc.
    reference_id = models.CharField(max_length=100, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
