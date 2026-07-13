# filename: createus_common/billing/services/entitlement.py

from __future__ import annotations

from typing import Optional

from django.db import transaction as db_transaction
from django.utils import timezone

from createus_common.billing import signals
from createus_common.billing.choices import SubscriptionStatus
from createus_common.billing.conf import get_store_transaction_model, get_subscription_model
from createus_common.billing.exceptions import SubscriptionException
from createus_common.billing.providers.base import (
    NormalizedRenewalInfo,
    NormalizedTransaction,
    StoreSubscriptionState,
)

_STATE_TO_STATUS: dict[StoreSubscriptionState, SubscriptionStatus] = {
    StoreSubscriptionState.ACTIVE: SubscriptionStatus.ACTIVE,
    StoreSubscriptionState.BILLING_RETRY: SubscriptionStatus.PAST_DUE,
    StoreSubscriptionState.GRACE_PERIOD: SubscriptionStatus.GRACE_PERIOD,
    StoreSubscriptionState.EXPIRED: SubscriptionStatus.EXPIRED,
    StoreSubscriptionState.REVOKED: SubscriptionStatus.REVOKED,
}


class AbstractEntitlementService:
    """
    Store-agnostic entitlement computation and persistence — the
    "server-side entitlement calculation" engine.

    Subclass per store integration (see
    ``createus_common.billing.services.apple.AppleSubscriptionSyncService``)
    and set ``provider_choice``. Everything in this class consumes only the
    normalized dataclasses from ``providers.base``, so the exact same state
    machine handles Apple today and Google Play once
    ``createus_common.billing.providers.google`` exists — only the
    provider-specific decode/verify step differs.

    Nothing here ever accepts a caller-supplied status/plan/boolean; the
    only inputs are values already produced by cryptographic verification
    or a live provider API call upstream of this class.
    """

    provider_choice: int  # createus_common.billing.choices.PaymentProvider value

    def find_subscription_by_external_id(self, original_transaction_id: str):
        model = get_subscription_model()
        return model.objects.filter(
            provider=self.provider_choice,
            external_subscription_id=original_transaction_id,
        ).first()

    def get_or_create_for_user(self, user, original_transaction_id: str):
        """
        Return the subscription row for this store subscription, scoped to
        ``user``, creating one if this is the first time we've seen it.

        Raises ``SubscriptionException`` if ``original_transaction_id`` is
        already linked to a *different* user. This is the guard against a
        malicious or buggy client submitting someone else's transaction id
        to claim their entitlement — re-linking a subscription to a new
        account is a deliberate support-flow operation on the concrete
        model, never an implicit side effect of an activation call.
        """
        model = get_subscription_model()
        existing = self.find_subscription_by_external_id(original_transaction_id)
        if existing is not None:
            if existing.user_id != user.id:
                raise SubscriptionException(
                    "This subscription is already linked to a different account."
                )
            return existing

        return model(
            user=user,
            provider=self.provider_choice,
            external_subscription_id=original_transaction_id,
            status=SubscriptionStatus.TRIALING,
        )

    def apply_state(
        self,
        subscription,
        *,
        state: StoreSubscriptionState,
        transaction: Optional[NormalizedTransaction],
        renewal_info: Optional[NormalizedRenewalInfo],
    ):
        """
        Compute and persist the new subscription fields for one verified
        ``(state, transaction, renewal_info)`` observation, record it in the
        transaction ledger (if configured), and fire the matching lifecycle
        signal.

        Idempotent in effect: applying the same observation twice (e.g.
        because a redelivered notification slipped past the notification
        log's dedupe) converges to the same subscription state rather than
        double-applying any change, since every field assignment here is a
        plain overwrite from the verified data, never an increment/append.
        """
        new_status = _STATE_TO_STATUS.get(state)
        if new_status is None:
            raise SubscriptionException(f"Unrecognized store subscription state: {state!r}")

        with db_transaction.atomic():
            previous_status = subscription.status
            is_new = subscription.pk is None

            subscription.status = new_status

            if transaction is not None:
                subscription.environment = transaction.environment
                subscription.product_id = transaction.product_id
                subscription.expires_at = transaction.expires_date
                if transaction.revocation_date is not None:
                    subscription.revoked_at = transaction.revocation_date
                    subscription.revocation_reason = transaction.revocation_reason
                if subscription.started_at is None:
                    subscription.started_at = (
                        transaction.original_purchase_date or transaction.purchase_date
                    )

            if renewal_info is not None:
                subscription.auto_renew_product_id = renewal_info.auto_renew_product_id
                subscription.auto_renew_status = renewal_info.auto_renew_status
                subscription.is_in_billing_retry_period = renewal_info.is_in_billing_retry_period
                subscription.grace_period_expires_at = renewal_info.grace_period_expires_date
                subscription.expiration_intent = renewal_info.expiration_intent

            if new_status == SubscriptionStatus.CANCELLED and subscription.cancelled_at is None:
                subscription.cancelled_at = timezone.now()

            subscription.save()
            self._record_transaction(transaction)

        self._fire_signal(
            subscription=subscription,
            transaction=transaction,
            previous_status=previous_status,
            new_status=new_status,
            is_new=is_new,
        )
        return subscription

    def _record_transaction(self, transaction: Optional[NormalizedTransaction]) -> None:
        if transaction is None:
            return
        model = get_store_transaction_model()
        if model is None:
            return
        model.objects.update_or_create(
            transaction_id=transaction.transaction_id,
            defaults=dict(
                provider=transaction.provider,
                environment=transaction.environment,
                original_transaction_id=transaction.original_transaction_id,
                product_id=transaction.product_id,
                subscription_group_id=transaction.subscription_group_id,
                quantity=transaction.quantity,
                transaction_type=transaction.transaction_type,
                in_app_ownership_type=transaction.in_app_ownership_type,
                transaction_reason=transaction.transaction_reason,
                purchase_date=transaction.purchase_date,
                original_purchase_date=transaction.original_purchase_date,
                expires_date=transaction.expires_date,
                offer_type=transaction.offer_type,
                offer_identifier=transaction.offer_identifier,
                is_upgraded=transaction.is_upgraded,
                revocation_date=transaction.revocation_date,
                revocation_reason=transaction.revocation_reason,
                storefront=transaction.storefront,
                storefront_id=transaction.storefront_id,
                price=transaction.price,
                currency=transaction.currency,
                signed_transaction_info=transaction.signed_transaction_info,
                decoded_payload=transaction.raw,
            ),
        )

    def _fire_signal(
        self,
        *,
        subscription,
        transaction: Optional[NormalizedTransaction],
        previous_status: SubscriptionStatus,
        new_status: SubscriptionStatus,
        is_new: bool,
    ) -> None:
        kwargs = dict(
            sender=type(self),
            subscription=subscription,
            transaction=transaction,
            previous_status=previous_status,
            new_status=new_status,
        )
        if new_status == SubscriptionStatus.ACTIVE:
            is_renewal = transaction is not None and transaction.transaction_reason == "RENEWAL"
            signal = signals.subscription_renewed if is_renewal else signals.subscription_activated
        elif new_status == SubscriptionStatus.GRACE_PERIOD:
            signal = signals.subscription_entered_grace_period
        elif new_status == SubscriptionStatus.PAST_DUE:
            signal = signals.subscription_entered_billing_retry
        elif new_status == SubscriptionStatus.CANCELLED:
            signal = signals.subscription_cancelled
        elif new_status == SubscriptionStatus.EXPIRED:
            signal = signals.subscription_expired
        elif new_status == SubscriptionStatus.REVOKED:
            signal = signals.subscription_revoked
        else:  # pragma: no cover - defensive, _STATE_TO_STATUS is exhaustive
            return
        signal.send(**kwargs)
