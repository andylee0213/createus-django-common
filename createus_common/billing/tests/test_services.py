# filename: createus_common/billing/tests/test_services.py

from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from createus_common.billing.choices import (
    CreditSourceType,
    CreditTransactionType,
    SubscriptionStatus,
)
from createus_common.billing.exceptions import (
    InsufficientCreditsException,
    SubscriptionException,
)
from createus_common.billing.services.credits import AbstractCreditService
from createus_common.billing.services.subscriptions import AbstractSubscriptionService


class _FakeBalance:
    def __init__(self, balance=0):
        self.balance = balance
        self.saved_fields = None

    def save(self, update_fields=None):
        self.saved_fields = update_fields


class _FakeCreditService(AbstractCreditService):
    """Minimal concrete subclass backed by plain objects instead of the DB."""

    def __init__(self, balance):
        self._balance = balance
        self.history = []

    def get_balance_instance(self, user):
        return self._balance

    def create_history_entry(
        self,
        user,
        transaction_type,
        source_type,
        amount,
        balance_after,
        description="",
        reference_id="",
    ):
        entry = SimpleNamespace(
            transaction_type=transaction_type,
            source_type=source_type,
            amount=amount,
            balance_after=balance_after,
            description=description,
            reference_id=reference_id,
        )
        self.history.append(entry)
        return entry


class AbstractCreditServiceGrantTests(TestCase):
    """TestCase (not SimpleTestCase): grant()/deduct() use @transaction.atomic,
    which requires a real DB connection even though the fake balance/history
    objects here never touch the database."""

    def test_grant_increments_balance_and_logs_history(self):
        balance = _FakeBalance(balance=100)
        service = _FakeCreditService(balance)

        result = service.grant(user=object(), amount=50, source_type=CreditSourceType.SUBSCRIPTION)

        self.assertEqual(result.balance, 150)
        self.assertEqual(len(service.history), 1)
        self.assertEqual(service.history[0].transaction_type, CreditTransactionType.GRANT)
        self.assertEqual(service.history[0].amount, 50)
        self.assertEqual(service.history[0].balance_after, 150)


class AbstractCreditServiceDeductTests(TestCase):
    def test_deduct_decrements_balance_and_logs_negative_amount(self):
        balance = _FakeBalance(balance=100)
        service = _FakeCreditService(balance)

        result = service.deduct(user=object(), amount=30, source_type=CreditSourceType.PURCHASE)

        self.assertEqual(result.balance, 70)
        self.assertEqual(service.history[0].transaction_type, CreditTransactionType.DEDUCT)
        self.assertEqual(service.history[0].amount, -30)

    def test_deduct_more_than_balance_raises_and_leaves_balance_unchanged(self):
        balance = _FakeBalance(balance=10)
        service = _FakeCreditService(balance)

        with self.assertRaises(InsufficientCreditsException):
            service.deduct(user=object(), amount=50, source_type=CreditSourceType.PURCHASE)

        self.assertEqual(balance.balance, 10)
        self.assertEqual(service.history, [])


class _FakeSubscription:
    def __init__(self, status):
        self.status = status
        self.cancelled_at = None
        self.saved_fields = None

    def save(self, update_fields=None):
        self.saved_fields = update_fields


class AbstractSubscriptionServiceTests(SimpleTestCase):
    def setUp(self):
        self.service = AbstractSubscriptionService()

    def test_activate_transitions_trialing_to_active(self):
        sub = _FakeSubscription(SubscriptionStatus.TRIALING)
        result = self.service.activate(sub)
        self.assertEqual(result.status, SubscriptionStatus.ACTIVE)

    def test_activate_rejects_already_active_subscription(self):
        sub = _FakeSubscription(SubscriptionStatus.ACTIVE)
        with self.assertRaises(SubscriptionException):
            self.service.activate(sub)

    def test_cancel_sets_status_and_cancelled_at(self):
        sub = _FakeSubscription(SubscriptionStatus.ACTIVE)
        result = self.service.cancel(sub)
        self.assertEqual(result.status, SubscriptionStatus.CANCELLED)
        self.assertIsNotNone(result.cancelled_at)

    def test_cancel_rejects_already_cancelled_subscription(self):
        sub = _FakeSubscription(SubscriptionStatus.CANCELLED)
        with self.assertRaises(SubscriptionException):
            self.service.cancel(sub)

    def test_cancel_with_save_false_does_not_persist(self):
        sub = _FakeSubscription(SubscriptionStatus.ACTIVE)
        self.service.cancel(sub, save=False)
        self.assertIsNone(sub.saved_fields)

    def test_expire_sets_status_expired(self):
        sub = _FakeSubscription(SubscriptionStatus.PAST_DUE)
        result = self.service.expire(sub)
        self.assertEqual(result.status, SubscriptionStatus.EXPIRED)
