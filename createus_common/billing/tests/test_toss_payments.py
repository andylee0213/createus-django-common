# filename: createus_common/billing/tests/test_toss_payments.py

import base64
from unittest.mock import Mock, patch

import httpx
from django.test import SimpleTestCase

from createus_common.billing.exceptions import (
    BillingKeyChargeException,
    BillingKeyIssueException,
    BillingKeyRevokeException,
    PaymentCancelException,
    PaymentConfirmException,
    ProviderConnectionException,
)
from createus_common.billing.providers.toss_payments import TossPaymentsClient


def _response(status_code: int, payload: dict) -> Mock:
    response = Mock(spec=httpx.Response)
    response.is_success = 200 <= status_code < 300
    response.json.return_value = payload
    return response


class TossPaymentsClientAuthTests(SimpleTestCase):
    def test_missing_secret_key_raises_value_error_on_call(self):
        client = TossPaymentsClient(secret_key=None)
        with self.assertRaises(ValueError):
            client.confirm_payment("pk_1", "order_1", 1000)

    @patch("createus_common.billing.providers.toss_payments.httpx.post")
    def test_authorization_header_is_basic_base64_of_secret_and_colon(self, mock_post):
        mock_post.return_value = _response(200, {"status": "DONE"})
        TossPaymentsClient(secret_key="test_secret").confirm_payment("pk_1", "order_1", 1000)
        headers = mock_post.call_args.kwargs["headers"]
        expected = "Basic " + base64.b64encode(b"test_secret:").decode()
        self.assertEqual(headers["Authorization"], expected)


class TossPaymentsClientConfirmPaymentTests(SimpleTestCase):
    def setUp(self):
        self.client = TossPaymentsClient(secret_key="test_secret")

    @patch("createus_common.billing.providers.toss_payments.httpx.post")
    def test_confirm_payment_success_returns_provider_payload(self, mock_post):
        mock_post.return_value = _response(200, {"paymentKey": "pk_1", "status": "DONE"})
        result = self.client.confirm_payment("pk_1", "order_1", 1000)
        self.assertEqual(result["status"], "DONE")
        called_url = mock_post.call_args.args[0]
        self.assertEqual(called_url, "https://api.tosspayments.com/v1/payments/confirm")
        called_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(
            called_payload, {"paymentKey": "pk_1", "orderId": "order_1", "amount": 1000}
        )

    @patch("createus_common.billing.providers.toss_payments.httpx.post")
    def test_confirm_payment_provider_error_raises_payment_confirm_exception(self, mock_post):
        mock_post.return_value = _response(
            400, {"code": "REJECT_CARD_COMPANY", "message": "denied"}
        )
        with self.assertRaises(PaymentConfirmException) as ctx:
            self.client.confirm_payment("pk_1", "order_1", 1000)
        self.assertEqual(ctx.exception.code, "REJECT_CARD_COMPANY")

    @patch("createus_common.billing.providers.toss_payments.httpx.post")
    def test_confirm_payment_network_error_raises_provider_connection_exception(self, mock_post):
        mock_post.side_effect = httpx.RequestError("boom")
        with self.assertRaises(ProviderConnectionException):
            self.client.confirm_payment("pk_1", "order_1", 1000)


class TossPaymentsClientCancelPaymentTests(SimpleTestCase):
    def setUp(self):
        self.client = TossPaymentsClient(secret_key="test_secret")

    @patch("createus_common.billing.providers.toss_payments.httpx.post")
    def test_cancel_payment_success(self, mock_post):
        mock_post.return_value = _response(200, {"status": "CANCELED"})
        result = self.client.cancel_payment("pk_1", "user request")
        self.assertEqual(result["status"], "CANCELED")

    @patch("createus_common.billing.providers.toss_payments.httpx.post")
    def test_cancel_payment_partial_includes_amount_and_currency(self, mock_post):
        mock_post.return_value = _response(200, {"status": "PARTIAL_CANCELED"})
        self.client.cancel_payment(
            "pk_1", "partial refund", cancel_amount=500, currency="KRW"
        )
        called_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(called_payload["cancelAmount"], 500)
        self.assertEqual(called_payload["currency"], "KRW")

    @patch("createus_common.billing.providers.toss_payments.httpx.post")
    def test_cancel_payment_provider_error_raises_payment_cancel_exception(self, mock_post):
        mock_post.return_value = _response(
            400, {"code": "ALREADY_CANCELED", "message": "already"}
        )
        with self.assertRaises(PaymentCancelException):
            self.client.cancel_payment("pk_1", "dup")


class TossPaymentsClientBillingKeyTests(SimpleTestCase):
    def setUp(self):
        self.client = TossPaymentsClient(secret_key="test_secret")

    @patch("createus_common.billing.providers.toss_payments.httpx.post")
    def test_issue_billing_key_success(self, mock_post):
        mock_post.return_value = _response(
            200, {"billingKey": "bk_1", "card": {"company": "Kookmin"}}
        )
        result = self.client.issue_billing_key("auth_1", "customer_1")
        self.assertEqual(result["billingKey"], "bk_1")

    @patch("createus_common.billing.providers.toss_payments.httpx.post")
    def test_issue_billing_key_error_raises_billing_key_issue_exception(self, mock_post):
        mock_post.return_value = _response(
            400, {"code": "INVALID_AUTH_KEY", "message": "bad"}
        )
        with self.assertRaises(BillingKeyIssueException):
            self.client.issue_billing_key("bad_auth", "customer_1")

    @patch("createus_common.billing.providers.toss_payments.httpx.post")
    def test_charge_billing_key_success_omits_unset_optional_fields(self, mock_post):
        mock_post.return_value = _response(200, {"status": "DONE"})
        result = self.client.charge_billing_key(
            billing_key="bk_1",
            customer_key="customer_1",
            amount=9900,
            order_id="order_1",
            order_name="Plan",
        )
        self.assertEqual(result["status"], "DONE")
        called_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(called_payload["taxFreeAmount"], 0)
        self.assertNotIn("customerEmail", called_payload)
        self.assertNotIn("customerName", called_payload)
        self.assertNotIn("customerIp", called_payload)

    @patch("createus_common.billing.providers.toss_payments.httpx.post")
    def test_charge_billing_key_error_raises_billing_key_charge_exception(self, mock_post):
        mock_post.return_value = _response(
            400, {"code": "EXCEED_MAX_DAILY_PAYMENT_COUNT", "message": "limit"}
        )
        with self.assertRaises(BillingKeyChargeException):
            self.client.charge_billing_key(
                billing_key="bk_1",
                customer_key="customer_1",
                amount=9900,
                order_id="order_1",
                order_name="Plan",
            )

    @patch("createus_common.billing.providers.toss_payments.httpx.delete")
    def test_revoke_billing_key_success_returns_none(self, mock_delete):
        mock_delete.return_value = _response(200, {})
        self.assertIsNone(self.client.revoke_billing_key("bk_1"))

    @patch("createus_common.billing.providers.toss_payments.httpx.delete")
    def test_revoke_billing_key_error_raises_billing_key_revoke_exception(self, mock_delete):
        mock_delete.return_value = _response(
            400, {"code": "NOT_FOUND_BILLING_KEY", "message": "missing"}
        )
        with self.assertRaises(BillingKeyRevokeException):
            self.client.revoke_billing_key("bk_missing")

    @patch("createus_common.billing.providers.toss_payments.httpx.delete")
    def test_revoke_billing_key_network_error_raises_provider_connection_exception(
        self, mock_delete
    ):
        mock_delete.side_effect = httpx.RequestError("boom")
        with self.assertRaises(ProviderConnectionException):
            self.client.revoke_billing_key("bk_1")
