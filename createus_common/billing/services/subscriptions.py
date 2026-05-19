# filename: createus_common/billing/services/subscriptions.py

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from createus_common.billing.choices import SubscriptionStatus
from createus_common.billing.exceptions import SubscriptionException

if TYPE_CHECKING:
    pass


class AbstractSubscriptionService:
    """
    Base service for subscription lifecycle management.

    Project apps subclass this, override the abstract methods, and inject
    their concrete model classes via the constructor.

    Example::

        class PocketLawSubscriptionService(AbstractSubscriptionService):
            def get_subscription(self, user):
                return UserSubscription.objects.filter(user=user).first()
            ...
    """

    def get_subscription(self, user: Any):
        raise NotImplementedError

    def activate(self, subscription: Any) -> Any:
        if subscription.status not in (
            SubscriptionStatus.TRIALING,
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.PAUSED,
        ):
            raise SubscriptionException(
                f"Cannot activate a subscription in status {subscription.status}."
            )
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.save(update_fields=["status", "updated_at"])
        return subscription

    def cancel(self, subscription: Any, *, save: bool = True) -> Any:
        if subscription.status == SubscriptionStatus.CANCELLED:
            raise SubscriptionException("Subscription is already cancelled.")
        from django.utils import timezone

        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = timezone.now()
        if save:
            subscription.save(update_fields=["status", "cancelled_at", "updated_at"])
        return subscription

    def expire(self, subscription: Any, *, save: bool = True) -> Any:
        subscription.status = SubscriptionStatus.EXPIRED
        if save:
            subscription.save(update_fields=["status", "updated_at"])
        return subscription
