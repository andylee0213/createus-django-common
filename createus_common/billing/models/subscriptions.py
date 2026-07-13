# filename: createus_common/billing/models/subscriptions.py

from django.db import models

from createus_common.models import TimeStampedModel
from createus_common.billing.choices import (
    BillingCurrency,
    ExpirationIntent,
    PaymentProvider,
    RevocationReason,
    StoreEnvironment,
    SubscriptionInterval,
    SubscriptionStatus,
)


class AbstractSubscriptionPlan(TimeStampedModel):
    """
    Defines a purchasable plan tier.  Project apps subclass this to add
    feature flags (e.g. max_seats, allowed_features).
    """

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    interval = models.IntegerField(choices=SubscriptionInterval.choices)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.IntegerField(
        choices=BillingCurrency.choices, default=BillingCurrency.KRW
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return self.name


class AbstractUserSubscription(TimeStampedModel):
    """
    Records a user's current subscription state.

    Project apps must add:
        user = models.OneToOneField(settings.AUTH_USER_MODEL, ...)
        plan = models.ForeignKey(<ConcretePlan>, ...)

    The fields below this line are populated only for store-based
    subscriptions (Apple App Store / Google Play) whose renewal, billing
    retry, and grace-period behavior is managed by the store rather than by
    a payment-provider webhook we control the semantics of.  They are all
    nullable/blank so non-store subscriptions (Toss, Stripe, PayPal) are
    unaffected.

    ``external_subscription_id`` holds the provider's durable subscription
    identifier: for Apple this is the ``originalTransactionId``, which stays
    constant across renewals, plan changes within a subscription group, and
    billing retries — it is NOT the same as an individual transaction id.
    """

    status = models.IntegerField(
        choices=SubscriptionStatus.choices, default=SubscriptionStatus.TRIALING
    )
    provider = models.IntegerField(
        choices=PaymentProvider.choices, null=True, blank=True
    )
    # Provider-assigned subscription identifier (e.g. Stripe sub_xxx, or
    # Apple's originalTransactionId).
    external_subscription_id = models.CharField(max_length=255, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # ── Store subscription (Apple / Google) fields ──────────────────────────
    environment = models.CharField(
        max_length=16, choices=StoreEnvironment.choices, blank=True, default=""
    )
    product_id = models.CharField(max_length=255, blank=True, default="")
    auto_renew_product_id = models.CharField(max_length=255, blank=True, default="")
    auto_renew_status = models.BooleanField(null=True, blank=True)
    is_in_billing_retry_period = models.BooleanField(null=True, blank=True)
    grace_period_expires_at = models.DateTimeField(null=True, blank=True)
    expiration_intent = models.IntegerField(
        choices=ExpirationIntent.choices, null=True, blank=True
    )
    revocation_reason = models.IntegerField(
        choices=RevocationReason.choices, null=True, blank=True
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def is_active(self) -> bool:
        return self.status == SubscriptionStatus.ACTIVE

    @property
    def has_entitlement(self) -> bool:
        """
        Whether the user should currently be granted paid access.

        Deliberately broader than ``is_active``: Apple's own guidance is to
        keep granting access during ``GRACE_PERIOD`` (the store is still
        retrying the charge and the user has not been told they lost
        access), but not during ``PAST_DUE``/billing-retry-without-grace,
        which the store already treats as lapsed.
        """
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE_PERIOD)
