# filename: createus_common/billing/models/store_notifications.py

from django.db import models

from createus_common.models import TimeStampedModel
from createus_common.billing.choices import (
    NotificationProcessingStatus,
    PaymentProvider,
    StoreEnvironment,
)


class AbstractStoreNotification(TimeStampedModel):
    """
    Raw + decoded log of every server-to-server notification received from
    a store (App Store Server Notifications V2, Google Play Real-time
    Developer Notifications).

    Serves two purposes:

    1. **Idempotency.** Apple redelivers notifications the receiving server
       does not acknowledge with 2xx quickly enough, and can otherwise
       redeliver duplicates. ``notification_uuid`` is unique per row, so a
       duplicate delivery becomes a no-op lookup rather than reprocessing
       (and re-firing signals for) the same event twice.
    2. **Audit trail.** ``signed_payload`` is kept verbatim so any dispute
       about what Apple told us, and when, can be answered without calling
       Apple again.
    """

    provider = models.IntegerField(choices=PaymentProvider.choices)
    environment = models.CharField(max_length=16, choices=StoreEnvironment.choices, blank=True, default="")

    notification_uuid = models.CharField(max_length=64, unique=True, db_index=True)
    notification_type = models.CharField(max_length=64)
    subtype = models.CharField(max_length=64, blank=True, default="")
    original_transaction_id = models.CharField(max_length=255, blank=True, default="", db_index=True)

    # Raw signedPayload string as delivered, verbatim.
    signed_payload = models.TextField()
    # Verified + decoded claims, JSON-safe.
    decoded_payload = models.JSONField(default=dict, blank=True)

    processing_status = models.IntegerField(
        choices=NotificationProcessingStatus.choices,
        default=NotificationProcessingStatus.PENDING,
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True, default="")

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["provider", "original_transaction_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.notification_type} [{self.notification_uuid}]"
