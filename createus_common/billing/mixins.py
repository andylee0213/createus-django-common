# filename: createus_common/billing/mixins.py

from rest_framework.exceptions import PermissionDenied

from createus_common.billing.choices import SubscriptionStatus


class ActiveSubscriptionMixin:
    """
    DRF view mixin that blocks access unless the requesting user has an
    active subscription.  The concrete view must implement
    ``get_user_subscription()`` returning the user's subscription instance
    (or None).
    """

    subscription_status_field = "status"

    def get_user_subscription(self):
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement get_user_subscription()"
        )

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        subscription = self.get_user_subscription()
        if subscription is None:
            raise PermissionDenied("An active subscription is required.")
        status = getattr(subscription, self.subscription_status_field, None)
        if status != SubscriptionStatus.ACTIVE:
            raise PermissionDenied("An active subscription is required.")


class CreditRequiredMixin:
    """
    DRF view mixin that blocks access when the requesting user has zero or
    negative credit balance.  The concrete view must implement
    ``get_credit_balance()`` returning an int.
    """

    def get_credit_balance(self) -> int:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement get_credit_balance()"
        )

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if self.get_credit_balance() <= 0:
            raise PermissionDenied("Insufficient credits.")
