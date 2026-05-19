# filename: createus_common/billing/models/subscriptions.py

from django.db import models

from createus_common.models import TimeStampedModel
from createus_common.billing.choices import (
    BillingCurrency,
    PaymentProvider,
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
    """

    status = models.IntegerField(
        choices=SubscriptionStatus.choices, default=SubscriptionStatus.TRIALING
    )
    provider = models.IntegerField(
        choices=PaymentProvider.choices, null=True, blank=True
    )
    # Provider-assigned subscription identifier (e.g. Stripe sub_xxx)
    external_subscription_id = models.CharField(max_length=255, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def is_active(self) -> bool:
        return self.status == SubscriptionStatus.ACTIVE
