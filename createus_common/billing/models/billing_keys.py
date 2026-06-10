# filename: createus_common/billing/models/billing_keys.py

from django.db import models

from createus_common.models import TimeStampedModel
from createus_common.billing.choices import PaymentProvider


class AbstractBillingKeyRecord(TimeStampedModel):
    """
    Provider-issued billingKey record for automatic (recurring) payments.

    Project apps subclass this and add:
        user = models.ForeignKey(settings.AUTH_USER_MODEL, ...)

    The ``billing_key`` value is sensitive — concrete apps should encrypt it
    at rest and must not write it to log output.  The raw Toss response from
    ``TossPaymentsClient.issue_billing_key()`` can be stored in
    ``raw_response`` for auditing; ensure secrets are redacted before logging.

    Responsibility boundaries
    -------------------------
    - This model owns the provider credential (billingKey / customerKey).
    - Subscription rules, renewal scheduling, and plan associations belong in
      the concrete project app.
    - ``TossPaymentsClient`` issues, charges, and revokes billing keys.
    - The project app orchestrates when those operations are called and handles
      the resulting subscription state changes.
    """

    provider = models.IntegerField(choices=PaymentProvider.choices)
    customer_key = models.CharField(max_length=300, db_index=True)
    billing_key = models.CharField(max_length=200)
    method = models.CharField(max_length=50, blank=True, default="")
    card_company = models.CharField(max_length=50, blank=True, default="")
    card_number = models.CharField(max_length=50, blank=True, default="")
    authenticated_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    raw_response = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"{self.get_provider_display()} billing key [{self.customer_key}]"
