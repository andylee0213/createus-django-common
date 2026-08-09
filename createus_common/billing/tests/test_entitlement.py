# filename: createus_common/billing/tests/test_entitlement.py

from datetime import datetime, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from createus_common.billing import signals
from createus_common.billing.choices import PaymentProvider, SubscriptionStatus
from createus_common.billing.exceptions import SubscriptionException
from createus_common.billing.providers.base import (
    NormalizedRenewalInfo,
    NormalizedTransaction,
    StoreSubscriptionState,
)
from createus_common.billing.services.entitlement import AbstractEntitlementService


class _FakeSubscription:
    def __init__(self, *, pk=None, status=SubscriptionStatus.TRIALING, user_id=1):
        self.pk = pk
        self.user_id = user_id
        self.status = status
        self.environment = ""
        self.product_id = ""
        self.expires_at = None
        self.revoked_at = None
        self.revocation_reason = None
        self.started_at = None
        self.auto_renew_product_id = ""
        self.auto_renew_status = None
        self.is_in_billing_retry_period = None
        self.grace_period_expires_at = None
        self.expiration_intent = None
        self.cancelled_at = None
        self.save_calls = 0

    def save(self, update_fields=None):
        self.save_calls += 1


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


def _renewal_info(**overrides) -> NormalizedRenewalInfo:
    defaults = dict(
        original_transaction_id="orig-1",
        auto_renew_product_id="com.cookthis.pro.monthly",
        auto_renew_status=True,
        expiration_intent=None,
        grace_period_expires_date=None,
        is_in_billing_retry_period=False,
        price_increase_status=None,
        environment="sandbox",
        renewal_date=None,
        renewal_price=2990,
        currency="USD",
    )
    defaults.update(overrides)
    return NormalizedRenewalInfo(**defaults)


class _TestEntitlementService(AbstractEntitlementService):
    provider_choice = PaymentProvider.APP_STORE


class ApplyStateTests(TestCase):
    """
    TestCase (not SimpleTestCase): ``apply_state`` wraps its body in
    ``transaction.atomic()``, which requires a real DB connection even
    though the fake subscription object here never touches the database.
    ``CREATEUS_BILLING_STORE_TRANSACTION_MODEL`` is unset in
    dev/devsettings.py, so ``_record_transaction`` is a documented no-op.
    """

    def setUp(self):
        self.service = _TestEntitlementService()

    def test_active_state_sets_active_status_and_fields(self):
        sub = _FakeSubscription()
        txn = _transaction()
        renewal = _renewal_info()
        result = self.service.apply_state(
            sub, state=StoreSubscriptionState.ACTIVE, transaction=txn, renewal_info=renewal
        )
        self.assertEqual(result.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(result.product_id, "com.cookthis.pro.monthly")
        self.assertEqual(result.expires_at, txn.expires_date)
        self.assertEqual(result.started_at, txn.original_purchase_date)
        self.assertTrue(result.auto_renew_status)
        self.assertEqual(result.save_calls, 1)

    def test_grace_period_state(self):
        sub = _FakeSubscription(status=SubscriptionStatus.ACTIVE)
        result = self.service.apply_state(
            sub,
            state=StoreSubscriptionState.GRACE_PERIOD,
            transaction=_transaction(),
            renewal_info=_renewal_info(is_in_billing_retry_period=True),
        )
        self.assertEqual(result.status, SubscriptionStatus.GRACE_PERIOD)
        self.assertTrue(result.is_in_billing_retry_period)

    def test_billing_retry_maps_to_past_due(self):
        sub = _FakeSubscription(status=SubscriptionStatus.ACTIVE)
        result = self.service.apply_state(
            sub,
            state=StoreSubscriptionState.BILLING_RETRY,
            transaction=_transaction(),
            renewal_info=None,
        )
        self.assertEqual(result.status, SubscriptionStatus.PAST_DUE)

    def test_expired_state(self):
        sub = _FakeSubscription(status=SubscriptionStatus.ACTIVE)
        result = self.service.apply_state(
            sub, state=StoreSubscriptionState.EXPIRED, transaction=_transaction(), renewal_info=None
        )
        self.assertEqual(result.status, SubscriptionStatus.EXPIRED)

    def test_revoked_state_sets_revocation_fields(self):
        sub = _FakeSubscription(status=SubscriptionStatus.ACTIVE)
        txn = _transaction(
            revocation_date=datetime(2024, 1, 15, tzinfo=dt_timezone.utc),
            revocation_reason=1,
        )
        result = self.service.apply_state(
            sub, state=StoreSubscriptionState.REVOKED, transaction=txn, renewal_info=None
        )
        self.assertEqual(result.status, SubscriptionStatus.REVOKED)
        self.assertEqual(result.revoked_at, txn.revocation_date)
        self.assertEqual(result.revocation_reason, 1)

    def test_started_at_not_overwritten_once_set(self):
        sub = _FakeSubscription(status=SubscriptionStatus.ACTIVE)
        sub.started_at = datetime(2020, 1, 1, tzinfo=dt_timezone.utc)
        self.service.apply_state(
            sub, state=StoreSubscriptionState.ACTIVE, transaction=_transaction(), renewal_info=None
        )
        self.assertEqual(sub.started_at, datetime(2020, 1, 1, tzinfo=dt_timezone.utc))

    def test_fires_activated_signal_for_purchase(self):
        received = []

        def _receiver(sender, **kwargs):
            received.append(kwargs)

        signals.subscription_activated.connect(_receiver)
        try:
            sub = _FakeSubscription()
            self.service.apply_state(
                sub,
                state=StoreSubscriptionState.ACTIVE,
                transaction=_transaction(transaction_reason="PURCHASE"),
                renewal_info=None,
            )
        finally:
            signals.subscription_activated.disconnect(_receiver)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["new_status"], SubscriptionStatus.ACTIVE)

    def test_fires_renewed_signal_for_renewal_transaction_reason(self):
        received = []

        def _receiver(sender, **kwargs):
            received.append(kwargs)

        signals.subscription_renewed.connect(_receiver)
        try:
            sub = _FakeSubscription(status=SubscriptionStatus.ACTIVE)
            self.service.apply_state(
                sub,
                state=StoreSubscriptionState.ACTIVE,
                transaction=_transaction(transaction_reason="RENEWAL"),
                renewal_info=None,
            )
        finally:
            signals.subscription_renewed.disconnect(_receiver)
        self.assertEqual(len(received), 1)

    def test_fires_revoked_signal(self):
        received = []

        def _receiver(sender, **kwargs):
            received.append(kwargs)

        signals.subscription_revoked.connect(_receiver)
        try:
            sub = _FakeSubscription(status=SubscriptionStatus.ACTIVE)
            self.service.apply_state(
                sub, state=StoreSubscriptionState.REVOKED, transaction=_transaction(), renewal_info=None
            )
        finally:
            signals.subscription_revoked.disconnect(_receiver)
        self.assertEqual(len(received), 1)

    def test_unrecognized_state_raises(self):
        sub = _FakeSubscription()
        with self.assertRaises(SubscriptionException):
            self.service.apply_state(sub, state=999, transaction=None, renewal_info=None)


class _FakeQuerySet:
    def __init__(self, result):
        self._result = result

    def first(self):
        return self._result


class _FakeManager:
    def __init__(self, result):
        self._result = result

    def filter(self, **kwargs):
        return _FakeQuerySet(self._result)


def _fake_model(result):
    class _FakeModel:
        objects = _FakeManager(result)

        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    return _FakeModel


class GetOrCreateForUserTests(SimpleTestCase):
    def setUp(self):
        self.service = _TestEntitlementService()

    def test_creates_new_subscription_when_none_exists(self):
        with patch(
            "createus_common.billing.services.entitlement.get_subscription_model",
            return_value=_fake_model(None),
        ):
            user = SimpleNamespace(id=42)
            result = self.service.get_or_create_for_user(user, "orig-1")
        self.assertEqual(result.user, user)
        self.assertEqual(result.external_subscription_id, "orig-1")
        self.assertEqual(result.provider, PaymentProvider.APP_STORE)
        self.assertEqual(result.status, SubscriptionStatus.TRIALING)

    def test_raises_when_linked_to_different_user(self):
        existing = SimpleNamespace(user_id=99)
        with patch(
            "createus_common.billing.services.entitlement.get_subscription_model",
            return_value=_fake_model(existing),
        ):
            user = SimpleNamespace(id=42)
            with self.assertRaises(SubscriptionException):
                self.service.get_or_create_for_user(user, "orig-1")

    def test_returns_existing_when_linked_to_same_user(self):
        existing = SimpleNamespace(user_id=42)
        with patch(
            "createus_common.billing.services.entitlement.get_subscription_model",
            return_value=_fake_model(existing),
        ):
            user = SimpleNamespace(id=42)
            result = self.service.get_or_create_for_user(user, "orig-1")
        self.assertIs(result, existing)
