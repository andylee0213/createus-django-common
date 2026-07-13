# filename: createus_common/billing/services/apple.py

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django.utils import timezone

from createus_common.billing.choices import NotificationProcessingStatus, PaymentProvider
from createus_common.billing.conf import get_store_notification_model
from createus_common.billing.exceptions import SubscriptionException
from createus_common.billing.providers.apple import AppleAppStoreProvider
from createus_common.billing.providers.base import SubscriptionStatusSnapshot
from createus_common.billing.services.entitlement import AbstractEntitlementService

_EPOCH = datetime.min.replace(tzinfo=dt_timezone.utc)


class AppleEntitlementService(AbstractEntitlementService):
    provider_choice = PaymentProvider.APP_STORE


class AppleSubscriptionSyncService:
    """
    High-level orchestration tying the Apple provider, the entitlement
    engine, and the notification ledger together. Views and background
    jobs call this; nothing below it is DRF- or HTTP-aware.
    """

    def __init__(
        self,
        provider: AppleAppStoreProvider | None = None,
        entitlement_service: AppleEntitlementService | None = None,
    ) -> None:
        self._provider = provider or AppleAppStoreProvider()
        self._entitlement = entitlement_service or AppleEntitlementService()

    def _select_snapshot(
        self,
        snapshots: list[SubscriptionStatusSnapshot],
        original_transaction_id: str,
    ) -> SubscriptionStatusSnapshot:
        """
        ``get_all_subscription_statuses`` returns every subscription in the
        group (e.g. if the user switched between monthly/yearly products
        within the same subscription group). Prefer the entry whose
        transaction actually matches the id we asked about; otherwise fall
        back to the most recently purchased entry.
        """
        for snapshot in snapshots:
            if (
                snapshot.transaction
                and snapshot.transaction.original_transaction_id == original_transaction_id
            ):
                return snapshot
        if not snapshots:
            raise SubscriptionException(
                "App Store returned no subscription status for this transaction."
            )
        return max(
            snapshots,
            key=lambda s: (s.transaction.purchase_date if s.transaction else None) or _EPOCH,
        )

    def activate_for_user(self, user, signed_transaction_info: str):
        """
        Securely activate/refresh a user's App Store subscription.

        The client submits only ``signed_transaction_info`` — the JWS from
        StoreKit 2's ``Transaction.jwsRepresentation`` — never a bare id,
        plan name, or boolean. Steps:

        1. Cryptographically verify the JWS came from Apple and matches our
           bundle id/environment. Rejects fabricated payloads outright.
        2. Call the App Store Server API for this subscription's *current*
           status — the actual source of truth. A client cannot advance its
           own entitlement by resending an old-but-validly-signed JWS from a
           since-cancelled/refunded subscription, because this step always
           re-derives the live state from Apple's servers rather than
           trusting anything about the submitted JWS beyond its identity
           (which original_transaction_id to look up).
        3. Feed the authoritative ``(state, transaction, renewal_info)`` into
           the entitlement engine.
        """
        client_transaction = self._provider.verify_and_decode_transaction(signed_transaction_info)

        snapshots = self._provider.get_subscription_statuses(
            client_transaction.original_transaction_id
        )
        snapshot = self._select_snapshot(snapshots, client_transaction.original_transaction_id)

        subscription = self._entitlement.get_or_create_for_user(
            user, client_transaction.original_transaction_id
        )
        return self._entitlement.apply_state(
            subscription,
            state=snapshot.state,
            transaction=snapshot.transaction or client_transaction,
            renewal_info=snapshot.renewal_info,
        )

    def handle_notification(self, signed_payload: str) -> None:
        """
        Process one App Store Server Notification V2 delivery.

        Verifies the outer envelope and any nested signed transaction/
        renewal info, deduplicates by ``notificationUUID`` against the
        configured notification-log model, and — when the notification
        carries transaction data — applies it through the same entitlement
        engine ``activate_for_user`` uses.

        No extra App Store Server API call is made here: a notification's
        embedded JWS carries the same cryptographic guarantee as a direct
        API response (Apple signs both the same way), so re-fetching would
        only add latency without adding trust.

        Raises on verification failure or processing error — the caller
        (the webhook view) must translate that into a non-2xx response so
        Apple retries; silently swallowing an error here would let a missed
        renewal/refund/revocation go permanently unapplied.
        """
        notification = self._provider.verify_and_decode_notification(signed_payload)

        log_model = get_store_notification_model()
        log_entry = None
        if log_model is not None:
            log_entry, created = log_model.objects.get_or_create(
                notification_uuid=notification.notification_uuid,
                defaults=dict(
                    provider=notification.provider,
                    environment=notification.environment,
                    notification_type=notification.notification_type,
                    subtype=notification.subtype,
                    original_transaction_id=(
                        notification.transaction.original_transaction_id
                        if notification.transaction
                        else ""
                    ),
                    signed_payload=signed_payload,
                    decoded_payload=notification.raw,
                ),
            )
            already_settled = log_entry.processing_status in (
                NotificationProcessingStatus.PROCESSED,
                NotificationProcessingStatus.IGNORED,
            )
            if not created and already_settled:
                # Genuine duplicate delivery of an already-handled
                # notification — no-op. (A PENDING/FAILED row from a
                # previous attempt that never completed falls through and
                # is retried below.)
                return

        try:
            if notification.transaction is not None and notification.state is not None:
                subscription = self._entitlement.find_subscription_by_external_id(
                    notification.transaction.original_transaction_id
                )
                if subscription is not None:
                    self._entitlement.apply_state(
                        subscription,
                        state=notification.state,
                        transaction=notification.transaction,
                        renewal_info=notification.renewal_info,
                    )
                    status_value = NotificationProcessingStatus.PROCESSED
                else:
                    # No local subscription linked yet (e.g. a renewal
                    # notification arrived before the app ever called
                    # activate_for_user). Safe to ignore: the next
                    # activate_for_user call or reconciliation sweep will
                    # pick up the authoritative state from Apple.
                    status_value = NotificationProcessingStatus.IGNORED
            else:
                # e.g. a TEST notification, or a `summary`/
                # `externalPurchaseToken` payload shape with no
                # per-subscription transaction attached.
                status_value = NotificationProcessingStatus.IGNORED

            if log_entry is not None:
                log_entry.processing_status = status_value
                log_entry.processed_at = timezone.now()
                log_entry.processing_error = ""
                log_entry.save(
                    update_fields=[
                        "processing_status",
                        "processed_at",
                        "processing_error",
                        "updated_at",
                    ]
                )
        except Exception as exc:
            if log_entry is not None:
                log_entry.processing_status = NotificationProcessingStatus.FAILED
                log_entry.processing_error = str(exc)
                log_entry.save(
                    update_fields=["processing_status", "processing_error", "updated_at"]
                )
            raise

    def sync_subscription(self, original_transaction_id: str):
        """
        Reconciliation entry point for background sync jobs (see
        ``createus_common.billing.management.commands.sync_appstore_subscriptions``).
        Re-fetches the authoritative status for one subscription and
        re-applies it — corrects drift from a missed/delayed webhook
        delivery without waiting for the user to reopen the app.
        """
        subscription = self._entitlement.find_subscription_by_external_id(original_transaction_id)
        if subscription is None:
            return None
        snapshots = self._provider.get_subscription_statuses(original_transaction_id)
        snapshot = self._select_snapshot(snapshots, original_transaction_id)
        return self._entitlement.apply_state(
            subscription,
            state=snapshot.state,
            transaction=snapshot.transaction,
            renewal_info=snapshot.renewal_info,
        )
