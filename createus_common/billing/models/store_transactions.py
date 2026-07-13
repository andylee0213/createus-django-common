# filename: createus_common/billing/models/store_transactions.py

from django.db import models

from createus_common.models import TimeStampedModel
from createus_common.billing.choices import (
    PaymentProvider,
    RevocationReason,
    StoreEnvironment,
    SubscriptionOfferType,
)


class AbstractStoreTransaction(TimeStampedModel):
    """
    Append-only ledger of every verified store transaction (initial
    purchase, renewal, refund, revocation) we have observed for a store
    subscription, whether learned from the client's activation call, the
    App Store Server API, or a Notifications V2 payload.

    This table is the audit trail the entitlement engine derives state
    from — it is intentionally decoupled from any concrete project's user
    model.  Subscriptions are looked up by
    ``(provider, original_transaction_id)`` against the concrete
    subscription model rather than via a FK here, since the concrete
    subscription model's class is project-specific and cannot be referenced
    from this shared, abstract model.

    ``transaction_id`` is unique per row (one row per distinct transaction
    Apple/Google ever issues); re-processing the same transaction (e.g. a
    duplicate notification delivery) must be a no-op update, not a duplicate
    insert — enforce this with ``get_or_create``/``update_or_create`` on
    ``(provider, transaction_id)`` in the service layer.
    """

    provider = models.IntegerField(choices=PaymentProvider.choices)
    environment = models.CharField(max_length=16, choices=StoreEnvironment.choices, blank=True, default="")

    # Durable subscription identifier (Apple: originalTransactionId).
    original_transaction_id = models.CharField(max_length=255, db_index=True)
    # This specific transaction/renewal instance.
    transaction_id = models.CharField(max_length=255, unique=True)

    product_id = models.CharField(max_length=255, blank=True, default="")
    subscription_group_id = models.CharField(max_length=255, blank=True, default="")

    quantity = models.PositiveIntegerField(default=1)
    # Apple's raw "type" string, e.g. "Auto-Renewable Subscription" — left
    # free-form (see choices.py comment) rather than an enforced enum.
    transaction_type = models.CharField(max_length=64, blank=True, default="")
    in_app_ownership_type = models.CharField(max_length=32, blank=True, default="")
    transaction_reason = models.CharField(max_length=32, blank=True, default="")

    purchase_date = models.DateTimeField(null=True, blank=True)
    original_purchase_date = models.DateTimeField(null=True, blank=True)
    expires_date = models.DateTimeField(null=True, blank=True)

    offer_type = models.IntegerField(choices=SubscriptionOfferType.choices, null=True, blank=True)
    offer_identifier = models.CharField(max_length=255, blank=True, default="")

    is_upgraded = models.BooleanField(default=False)

    revocation_date = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.IntegerField(choices=RevocationReason.choices, null=True, blank=True)

    storefront = models.CharField(max_length=8, blank=True, default="")
    storefront_id = models.CharField(max_length=64, blank=True, default="")
    price = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=8, blank=True, default="")

    # Raw JWS strings, kept for re-verification/audit. Not sensitive
    # (they carry no shared secret), unlike a Toss billingKey.
    signed_transaction_info = models.TextField(blank=True, default="")
    signed_renewal_info = models.TextField(blank=True, default="")
    # Fully-decoded claims, JSON-safe (enums serialized to their raw value).
    decoded_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["provider", "original_transaction_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_provider_display()} txn [{self.transaction_id}]"
