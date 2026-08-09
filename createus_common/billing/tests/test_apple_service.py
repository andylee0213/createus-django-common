# filename: createus_common/billing/tests/test_apple_service.py

from datetime import datetime, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from createus_common.billing.choices import NotificationProcessingStatus, PaymentProvider
from createus_common.billing.exceptions import SubscriptionException
from createus_common.billing.providers.base import (
    NormalizedNotification,
    NormalizedTransaction,
    StoreSubscriptionState,
    SubscriptionStatusSnapshot,
)
from createus_common.billing.services.apple import AppleSubscriptionSyncService


def _transaction(**overrides) -> NormalizedTransaction:
    defaults = dict(
        provider=PaymentProvider.APP_STORE,
        environment="sandbox",
        original_transaction_id="orig-1",
        transaction_id="txn-1",
        product_id="com.cookthis.pro.monthly",
        purchase_date=datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
        original_purchase_date=datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
        expires_date=datetime(2024, 2, 1, tzinfo=dt_timezone.utc),
        quantity=1,
        transaction_type="Auto-Renewable Subscription",
        in_app_ownership_type="PURCHASED",
        subscription_group_id="group1",
        offer_type=None,
        offer_identifier="",
        revocation_date=None,
        revocation_reason=None,
        is_upgraded=False,
        transaction_reason="PURCHASE",
        storefront="USA",
        storefront_id="143441",
        price=2990,
        currency="USD",
    )
    defaults.update(overrides)
    return NormalizedTransaction(**defaults)


class _FakeLogEntry:
    def __init__(self, notification_uuid, processing_status=NotificationProcessingStatus.PENDING, **kwargs):
        self.notification_uuid = notification_uuid
        self.processing_status = processing_status
        self.processing_error = ""
        self.processed_at = None
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.saved_fields = None

    def save(self, update_fields=None):
        self.saved_fields = update_fields


class _FakeLogManager:
    def __init__(self):
        self.store = {}

    def get_or_create(self, notification_uuid, defaults):
        if notification_uuid in self.store:
            return self.store[notification_uuid], False
        entry = _FakeLogEntry(notification_uuid, **defaults)
        self.store[notification_uuid] = entry
        return entry, True


def _fake_log_model(manager=None):
    manager = manager or _FakeLogManager()

    class _Model:
        objects = manager

    return _Model


class ActivateForUserTests(SimpleTestCase):
    def test_verifies_fetches_status_and_delegates_to_entitlement_engine(self):
        client_transaction = _transaction(transaction_id="txn-client")
        canonical_transaction = _transaction(transaction_id="txn-canonical")
        snapshot = SubscriptionStatusSnapshot(
            state=StoreSubscriptionState.ACTIVE, transaction=canonical_transaction, renewal_info=None
        )

        provider = Mock()
        provider.verify_and_decode_transaction.return_value = client_transaction
        provider.get_subscription_statuses.return_value = [snapshot]

        entitlement = Mock()
        subscription = SimpleNamespace()
        entitlement.get_or_create_for_user.return_value = subscription
        entitlement.apply_state.return_value = subscription

        service = AppleSubscriptionSyncService(provider=provider, entitlement_service=entitlement)
        user = SimpleNamespace(id=1)
        result = service.activate_for_user(user, "jws-from-client")

        provider.verify_and_decode_transaction.assert_called_once_with("jws-from-client")
        provider.get_subscription_statuses.assert_called_once_with("orig-1")
        entitlement.get_or_create_for_user.assert_called_once_with(user, "orig-1")
        entitlement.apply_state.assert_called_once_with(
            subscription,
            state=StoreSubscriptionState.ACTIVE,
            transaction=canonical_transaction,
            renewal_info=None,
        )
        self.assertIs(result, subscription)

    def test_propagates_cross_account_rejection(self):
        provider = Mock()
        provider.verify_and_decode_transaction.return_value = _transaction()
        provider.get_subscription_statuses.return_value = [
            SubscriptionStatusSnapshot(
                state=StoreSubscriptionState.ACTIVE, transaction=_transaction(), renewal_info=None
            )
        ]
        entitlement = Mock()
        entitlement.get_or_create_for_user.side_effect = SubscriptionException("already linked")

        service = AppleSubscriptionSyncService(provider=provider, entitlement_service=entitlement)
        with self.assertRaises(SubscriptionException):
            service.activate_for_user(SimpleNamespace(id=1), "jws")

    def test_raises_when_apple_returns_no_snapshots(self):
        provider = Mock()
        provider.verify_and_decode_transaction.return_value = _transaction()
        provider.get_subscription_statuses.return_value = []
        entitlement = Mock()

        service = AppleSubscriptionSyncService(provider=provider, entitlement_service=entitlement)
        with self.assertRaises(SubscriptionException):
            service.activate_for_user(SimpleNamespace(id=1), "jws")

    def test_selects_snapshot_matching_requested_original_transaction_id(self):
        matching = SubscriptionStatusSnapshot(
            state=StoreSubscriptionState.ACTIVE,
            transaction=_transaction(original_transaction_id="orig-1", transaction_id="a"),
            renewal_info=None,
        )
        other = SubscriptionStatusSnapshot(
            state=StoreSubscriptionState.EXPIRED,
            transaction=_transaction(original_transaction_id="orig-2", transaction_id="b"),
            renewal_info=None,
        )
        provider = Mock()
        provider.verify_and_decode_transaction.return_value = _transaction(
            original_transaction_id="orig-1"
        )
        provider.get_subscription_statuses.return_value = [other, matching]
        entitlement = Mock()
        entitlement.get_or_create_for_user.return_value = SimpleNamespace()
        entitlement.apply_state.side_effect = lambda sub, **kwargs: kwargs

        service = AppleSubscriptionSyncService(provider=provider, entitlement_service=entitlement)
        result = service.activate_for_user(SimpleNamespace(id=1), "jws")
        self.assertEqual(result["state"], StoreSubscriptionState.ACTIVE)
        self.assertEqual(result["transaction"].transaction_id, "a")


class HandleNotificationTests(SimpleTestCase):
    def _notification(self, **overrides):
        defaults = dict(
            provider=PaymentProvider.APP_STORE,
            notification_uuid="uuid-1",
            notification_type="DID_RENEW",
            subtype="",
            environment="sandbox",
            transaction=_transaction(),
            renewal_info=None,
            state=StoreSubscriptionState.ACTIVE,
            raw={},
        )
        defaults.update(overrides)
        return NormalizedNotification(**defaults)

    def test_applies_state_when_subscription_exists(self):
        provider = Mock()
        provider.verify_and_decode_notification.return_value = self._notification()
        entitlement = Mock()
        subscription = SimpleNamespace()
        entitlement.find_subscription_by_external_id.return_value = subscription

        with patch(
            "createus_common.billing.services.apple.get_store_notification_model", return_value=None
        ):
            service = AppleSubscriptionSyncService(provider=provider, entitlement_service=entitlement)
            service.handle_notification("signed-payload")

        entitlement.apply_state.assert_called_once()

    def test_ignores_when_no_local_subscription_linked(self):
        provider = Mock()
        provider.verify_and_decode_notification.return_value = self._notification()
        entitlement = Mock()
        entitlement.find_subscription_by_external_id.return_value = None

        with patch(
            "createus_common.billing.services.apple.get_store_notification_model", return_value=None
        ):
            service = AppleSubscriptionSyncService(provider=provider, entitlement_service=entitlement)
            service.handle_notification("signed-payload")

        entitlement.apply_state.assert_not_called()

    def test_duplicate_processed_delivery_is_a_noop(self):
        manager = _FakeLogManager()
        manager.store["uuid-1"] = _FakeLogEntry(
            "uuid-1", processing_status=NotificationProcessingStatus.PROCESSED
        )
        log_model = _fake_log_model(manager)

        provider = Mock()
        provider.verify_and_decode_notification.return_value = self._notification()
        entitlement = Mock()

        with patch(
            "createus_common.billing.services.apple.get_store_notification_model",
            return_value=log_model,
        ):
            service = AppleSubscriptionSyncService(provider=provider, entitlement_service=entitlement)
            service.handle_notification("signed-payload")

        entitlement.find_subscription_by_external_id.assert_not_called()
        entitlement.apply_state.assert_not_called()

    def test_previously_failed_delivery_is_retried(self):
        manager = _FakeLogManager()
        manager.store["uuid-1"] = _FakeLogEntry(
            "uuid-1", processing_status=NotificationProcessingStatus.FAILED
        )
        log_model = _fake_log_model(manager)

        provider = Mock()
        provider.verify_and_decode_notification.return_value = self._notification()
        entitlement = Mock()
        entitlement.find_subscription_by_external_id.return_value = SimpleNamespace()

        with patch(
            "createus_common.billing.services.apple.get_store_notification_model",
            return_value=log_model,
        ):
            service = AppleSubscriptionSyncService(provider=provider, entitlement_service=entitlement)
            service.handle_notification("signed-payload")

        entitlement.apply_state.assert_called_once()
        self.assertEqual(
            manager.store["uuid-1"].processing_status, NotificationProcessingStatus.PROCESSED
        )

    def test_processing_error_marks_entry_failed_and_reraises(self):
        manager = _FakeLogManager()
        log_model = _fake_log_model(manager)

        provider = Mock()
        provider.verify_and_decode_notification.return_value = self._notification()
        entitlement = Mock()
        entitlement.find_subscription_by_external_id.return_value = SimpleNamespace()
        entitlement.apply_state.side_effect = RuntimeError("db exploded")

        with patch(
            "createus_common.billing.services.apple.get_store_notification_model",
            return_value=log_model,
        ):
            service = AppleSubscriptionSyncService(provider=provider, entitlement_service=entitlement)
            with self.assertRaises(RuntimeError):
                service.handle_notification("signed-payload")

        entry = manager.store["uuid-1"]
        self.assertEqual(entry.processing_status, NotificationProcessingStatus.FAILED)
        self.assertIn("db exploded", entry.processing_error)

    def test_notification_without_transaction_is_ignored(self):
        provider = Mock()
        provider.verify_and_decode_notification.return_value = self._notification(
            transaction=None, state=None, notification_type="TEST"
        )
        entitlement = Mock()

        with patch(
            "createus_common.billing.services.apple.get_store_notification_model", return_value=None
        ):
            service = AppleSubscriptionSyncService(provider=provider, entitlement_service=entitlement)
            service.handle_notification("signed-payload")

        entitlement.find_subscription_by_external_id.assert_not_called()
        entitlement.apply_state.assert_not_called()


class SyncSubscriptionTests(SimpleTestCase):
    def test_returns_none_when_subscription_not_found_locally(self):
        provider = Mock()
        entitlement = Mock()
        entitlement.find_subscription_by_external_id.return_value = None

        service = AppleSubscriptionSyncService(provider=provider, entitlement_service=entitlement)
        result = service.sync_subscription("orig-1")

        self.assertIsNone(result)
        provider.get_subscription_statuses.assert_not_called()

    def test_reapplies_authoritative_state_when_found(self):
        subscription = SimpleNamespace()
        snapshot = SubscriptionStatusSnapshot(
            state=StoreSubscriptionState.EXPIRED, transaction=_transaction(), renewal_info=None
        )
        provider = Mock()
        provider.get_subscription_statuses.return_value = [snapshot]
        entitlement = Mock()
        entitlement.find_subscription_by_external_id.return_value = subscription
        entitlement.apply_state.return_value = subscription

        service = AppleSubscriptionSyncService(provider=provider, entitlement_service=entitlement)
        result = service.sync_subscription("orig-1")

        entitlement.apply_state.assert_called_once_with(
            subscription,
            state=StoreSubscriptionState.EXPIRED,
            transaction=snapshot.transaction,
            renewal_info=None,
        )
        self.assertIs(result, subscription)
