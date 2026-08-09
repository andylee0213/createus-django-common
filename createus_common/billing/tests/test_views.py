# filename: createus_common/billing/tests/test_views.py

from datetime import datetime, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from createus_common.billing.exceptions import (
    StoreAPIException,
    SubscriptionException,
    TransactionVerificationException,
)
from createus_common.billing.views import (
    AppStoreActivateSubscriptionView,
    AppStoreServerNotificationsView,
)

User = get_user_model()


class AppStoreActivateSubscriptionViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="alice", password="pw")

    def _post(self, data, authenticate=True):
        request = self.factory.post("/app-store/activate/", data, format="json")
        if authenticate:
            force_authenticate(request, user=self.user)
        return AppStoreActivateSubscriptionView.as_view()(request)

    def test_requires_authentication(self):
        response = self._post({"signed_transaction_info": "jws"}, authenticate=False)
        self.assertIn(response.status_code, (401, 403))

    def test_rejects_missing_signed_transaction_info(self):
        response = self._post({})
        self.assertEqual(response.status_code, 400)

    def test_returns_400_on_verification_failure(self):
        with patch("createus_common.billing.views.AppleSubscriptionSyncService") as mock_cls:
            mock_cls.return_value.activate_for_user.side_effect = TransactionVerificationException(
                "bad signature"
            )
            response = self._post({"signed_transaction_info": "jws"})
        self.assertEqual(response.status_code, 400)

    def test_returns_502_on_store_api_failure(self):
        with patch("createus_common.billing.views.AppleSubscriptionSyncService") as mock_cls:
            mock_cls.return_value.activate_for_user.side_effect = StoreAPIException(
                message="apple down"
            )
            response = self._post({"signed_transaction_info": "jws"})
        self.assertEqual(response.status_code, 502)

    def test_returns_409_on_cross_account_conflict(self):
        with patch("createus_common.billing.views.AppleSubscriptionSyncService") as mock_cls:
            mock_cls.return_value.activate_for_user.side_effect = SubscriptionException(
                "already linked to a different account"
            )
            response = self._post({"signed_transaction_info": "jws"})
        self.assertEqual(response.status_code, 409)

    def test_returns_serialized_subscription_on_success(self):
        fake_subscription = SimpleNamespace(
            provider=4,
            status=2,
            external_subscription_id="orig-1",
            product_id="com.cookthis.pro.monthly",
            environment="sandbox",
            started_at=datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
            expires_at=datetime(2024, 2, 1, tzinfo=dt_timezone.utc),
            cancelled_at=None,
            auto_renew_status=True,
            is_in_billing_retry_period=False,
            grace_period_expires_at=None,
            has_entitlement=True,
            get_provider_display=lambda: "Apple App Store",
            get_status_display=lambda: "Active",
        )
        with patch("createus_common.billing.views.AppleSubscriptionSyncService") as mock_cls:
            mock_cls.return_value.activate_for_user.return_value = fake_subscription
            response = self._post({"signed_transaction_info": "jws"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["external_subscription_id"], "orig-1")
        self.assertTrue(response.data["has_entitlement"])
        self.assertEqual(response.data["provider"], "Apple App Store")


class AppStoreServerNotificationsViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def _post(self, data):
        request = self.factory.post("/app-store/notifications/", data, format="json")
        return AppStoreServerNotificationsView.as_view()(request)

    def test_rejects_missing_signed_payload(self):
        response = self._post({})
        self.assertEqual(response.status_code, 400)

    def test_returns_200_on_success_without_auth(self):
        with patch("createus_common.billing.views.AppleSubscriptionSyncService") as mock_cls:
            mock_cls.return_value.handle_notification.return_value = None
            response = self._post({"signedPayload": "signed-jws"})
        self.assertEqual(response.status_code, 200)

    def test_returns_400_on_verification_failure(self):
        with patch("createus_common.billing.views.AppleSubscriptionSyncService") as mock_cls:
            mock_cls.return_value.handle_notification.side_effect = TransactionVerificationException(
                "bad signature"
            )
            response = self._post({"signedPayload": "bad-jws"})
        self.assertEqual(response.status_code, 400)

    def test_returns_500_on_generic_billing_failure_so_apple_retries(self):
        with patch("createus_common.billing.views.AppleSubscriptionSyncService") as mock_cls:
            mock_cls.return_value.handle_notification.side_effect = SubscriptionException("boom")
            response = self._post({"signedPayload": "jws"})
        self.assertEqual(response.status_code, 500)
