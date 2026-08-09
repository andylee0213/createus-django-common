# filename: createus_common/billing/tests/test_paypal_client.py

import time
from unittest.mock import Mock, patch

import httpx
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from createus_common.billing.exceptions import (
    PayPalAuthException,
    PayPalOrderException,
    PayPalSubscriptionException,
    ProviderConnectionException,
    WebhookVerificationException,
)
from createus_common.billing.providers.paypal import conf as paypal_conf
from createus_common.billing.providers.paypal.client import _TOKEN_CACHE, PayPalClient


def _response(status_code: int, payload) -> Mock:
    response = Mock(spec=httpx.Response)
    response.status_code = status_code
    response.is_success = 200 <= status_code < 300
    if isinstance(payload, Exception):
        response.json.side_effect = payload
    else:
        response.json.return_value = payload
    return response


def _client(**overrides) -> PayPalClient:
    kwargs = {
        "mode": "sandbox",
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "webhook_id": "WH-TEST-1",
    }
    kwargs.update(overrides)
    return PayPalClient(**kwargs)


def _valid_token_response():
    return _response(200, {"access_token": "A21token", "expires_in": 32400, "token_type": "Bearer"})


class _TokenCacheIsolationMixin:
    """Every test gets a clean process-local token cache."""

    def setUp(self):
        super().setUp()
        _TOKEN_CACHE.clear()
        self.addCleanup(_TOKEN_CACHE.clear)


# ─── conf.py ──────────────────────────────────────────────────────────────


class ConfTests(SimpleTestCase):
    @override_settings(PAYPAL_ENABLED=False)
    def test_disabled_by_default_semantics(self):
        self.assertFalse(paypal_conf.is_enabled())

    @override_settings(PAYPAL_ENABLED=True, PAYPAL_MODE="sandbox")
    def test_mode_sandbox(self):
        self.assertEqual(paypal_conf.get_mode(), "sandbox")
        self.assertEqual(
            paypal_conf.get_base_url(), "https://api-m.sandbox.paypal.com"
        )

    @override_settings(PAYPAL_MODE="live")
    def test_mode_live(self):
        self.assertEqual(paypal_conf.get_mode(), "live")
        self.assertEqual(paypal_conf.get_base_url(), "https://api-m.paypal.com")

    @override_settings(PAYPAL_MODE="production")
    def test_invalid_mode_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            paypal_conf.get_mode()

    @override_settings(PAYPAL_CLIENT_ID="")
    def test_missing_client_id_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            paypal_conf.get_client_id()

    @override_settings(PAYPAL_CLIENT_SECRET="")
    def test_missing_client_secret_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            paypal_conf.get_client_secret()

    @override_settings(PAYPAL_WEBHOOK_ID="")
    def test_missing_webhook_id_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            paypal_conf.get_webhook_id()

    @override_settings(PAYPAL_ENABLED=False)
    def test_check_configuration_noop_when_disabled(self):
        paypal_conf.check_configuration()  # must not raise even with nothing else set

    @override_settings(
        PAYPAL_ENABLED=True,
        PAYPAL_MODE="sandbox",
        PAYPAL_CLIENT_ID="",
        PAYPAL_CLIENT_SECRET="",
        PAYPAL_WEBHOOK_ID="",
    )
    def test_check_configuration_fails_closed_when_enabled_but_incomplete(self):
        with self.assertRaises(ImproperlyConfigured):
            paypal_conf.check_configuration()

    @override_settings(PAYPAL_ENABLED=True, PAYPAL_ONE_TIME_ENABLED=False)
    def test_one_time_flag_overrides_enabled(self):
        self.assertFalse(paypal_conf.is_one_time_enabled())
        self.assertTrue(paypal_conf.is_enabled())

    @override_settings(PAYPAL_ENABLED=True)
    def test_subscriptions_flag_defaults_to_enabled(self):
        self.assertTrue(paypal_conf.is_subscriptions_enabled())


# ─── OAuth2 token retrieval & caching ──────────────────────────────────────


class TokenTests(_TokenCacheIsolationMixin, SimpleTestCase):
    @patch("httpx.Client.post")
    def test_sandbox_mode_uses_sandbox_token_url(self, mock_post):
        mock_post.return_value = _valid_token_response()
        client = _client(mode="sandbox")
        client._get_access_token()
        self.assertEqual(
            mock_post.call_args.args[0],
            "https://api-m.sandbox.paypal.com/v1/oauth2/token",
        )

    @patch("httpx.Client.post")
    def test_live_mode_uses_live_token_url(self, mock_post):
        mock_post.return_value = _valid_token_response()
        client = _client(mode="live")
        client._get_access_token()
        self.assertEqual(
            mock_post.call_args.args[0], "https://api-m.paypal.com/v1/oauth2/token"
        )

    @patch("httpx.Client.post")
    def test_uses_basic_auth_of_client_id_and_secret(self, mock_post):
        mock_post.return_value = _valid_token_response()
        _client(client_id="cid", client_secret="csecret")._get_access_token()
        self.assertEqual(mock_post.call_args.kwargs["auth"], ("cid", "csecret"))

    @patch("httpx.Client.post")
    def test_token_is_cached_across_calls(self, mock_post):
        mock_post.return_value = _valid_token_response()
        client = _client()
        token1 = client._get_access_token()
        token2 = client._get_access_token()
        self.assertEqual(token1, token2)
        self.assertEqual(mock_post.call_count, 1)

    @patch("httpx.Client.post")
    def test_token_refetched_after_expiry_safety_margin(self, mock_post):
        mock_post.return_value = _response(
            200, {"access_token": "short-lived", "expires_in": 30, "token_type": "Bearer"}
        )
        client = _client()
        client._get_access_token()
        # expires_in=30 is inside the 60s safety margin, so the very next
        # call must refetch rather than serve the (nearly-expired) cache.
        client._get_access_token()
        self.assertEqual(mock_post.call_count, 2)

    @patch("httpx.Client.post")
    def test_different_client_ids_get_independent_cache_entries(self, mock_post):
        mock_post.return_value = _valid_token_response()
        _client(client_id="cid-a")._get_access_token()
        _client(client_id="cid-b")._get_access_token()
        self.assertEqual(mock_post.call_count, 2)

    @patch("httpx.Client.post")
    def test_sandbox_and_live_get_independent_cache_entries(self, mock_post):
        mock_post.return_value = _valid_token_response()
        _client(mode="sandbox")._get_access_token()
        _client(mode="live")._get_access_token()
        self.assertEqual(mock_post.call_count, 2)

    @patch("httpx.Client.post")
    def test_provider_error_raises_paypal_auth_exception(self, mock_post):
        mock_post.return_value = _response(
            401, {"error": "invalid_client", "error_description": "Client Authentication failed"}
        )
        with self.assertRaises(PayPalAuthException) as ctx:
            _client()._get_access_token()
        self.assertEqual(ctx.exception.code, "invalid_client")

    @patch("httpx.Client.post")
    def test_network_error_raises_provider_connection_exception(self, mock_post):
        mock_post.side_effect = httpx.RequestError("boom")
        with self.assertRaises(ProviderConnectionException):
            _client()._get_access_token()

    @patch("httpx.Client.post")
    def test_timeout_raises_provider_connection_exception(self, mock_post):
        mock_post.side_effect = httpx.TimeoutException("timed out")
        with self.assertRaises(ProviderConnectionException):
            _client()._get_access_token()

    @patch("httpx.Client.post")
    def test_non_json_error_body_does_not_crash(self, mock_post):
        mock_post.return_value = _response(500, ValueError("not json"))
        with self.assertRaises(PayPalAuthException):
            _client()._get_access_token()

    @patch("httpx.Client.post")
    def test_client_secret_never_appears_in_exception_message(self, mock_post):
        mock_post.return_value = _response(
            401, {"error": "invalid_client", "error_description": "denied"}
        )
        secret = "super-secret-value-should-not-leak"
        with self.assertRaises(PayPalAuthException) as ctx:
            _client(client_secret=secret)._get_access_token()
        self.assertNotIn(secret, str(ctx.exception))
        self.assertNotIn(secret, repr(ctx.exception.raw))

    @patch("httpx.Client.post")
    def test_malformed_token_response_raises(self, mock_post):
        mock_post.return_value = _response(200, {"token_type": "Bearer"})
        with self.assertRaises(PayPalAuthException):
            _client()._get_access_token()


# ─── Orders v2 ──────────────────────────────────────────────────────────


class OrdersTests(_TokenCacheIsolationMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch("httpx.Client.post")
        self.mock_post = patcher.start()
        self.addCleanup(patcher.stop)

        request_patcher = patch(
            "httpx.Client.request"
        )
        self.mock_request = request_patcher.start()
        self.addCleanup(request_patcher.stop)

        self.mock_post.return_value = _valid_token_response()
        self.client = _client()

    def test_create_order_sends_db_amount_and_currency(self):
        self.mock_request.return_value = _response(
            201, {"id": "ORDER-1", "status": "CREATED"}
        )
        result = self.client.create_order(
            amount="49.00", currency="USD", reference_id="plcl_abc", request_id="plcl_abc"
        )
        self.assertEqual(result["id"], "ORDER-1")
        call = self.mock_request.call_args
        self.assertEqual(call.args[0], "POST")
        self.assertEqual(call.args[1], "https://api-m.sandbox.paypal.com/v2/checkout/orders")
        body = call.kwargs["json"]
        self.assertEqual(body["purchase_units"][0]["amount"]["value"], "49.00")
        self.assertEqual(body["purchase_units"][0]["amount"]["currency_code"], "USD")
        self.assertEqual(body["intent"], "CAPTURE")

    def test_create_order_sends_deterministic_request_id_header(self):
        self.mock_request.return_value = _response(201, {"id": "ORDER-1"})
        self.client.create_order(
            amount="10.00", currency="USD", reference_id="ref-1", request_id="deterministic-1"
        )
        headers = self.mock_request.call_args.kwargs["headers"]
        self.assertEqual(headers["PayPal-Request-Id"], "deterministic-1")

    def test_repeated_request_id_sends_identical_header_each_time(self):
        """
        The client does not itself dedupe — PayPal does, server-side, keyed
        on this header — so calling twice with the same request_id must
        send the exact same header both times (dedup is proven at the
        provider, not skipped locally).
        """
        self.mock_request.return_value = _response(201, {"id": "ORDER-1"})
        self.client.create_order(amount="10.00", currency="USD", reference_id="r", request_id="dup-1")
        self.client.create_order(amount="10.00", currency="USD", reference_id="r", request_id="dup-1")
        headers_1 = self.mock_request.call_args_list[0].kwargs["headers"]
        headers_2 = self.mock_request.call_args_list[1].kwargs["headers"]
        self.assertEqual(headers_1["PayPal-Request-Id"], headers_2["PayPal-Request-Id"])
        self.assertEqual(self.mock_request.call_count, 2)

    def test_get_order(self):
        self.mock_request.return_value = _response(200, {"id": "ORDER-1", "status": "APPROVED"})
        result = self.client.get_order("ORDER-1")
        self.assertEqual(result["status"], "APPROVED")
        self.assertEqual(
            self.mock_request.call_args.args[1],
            "https://api-m.sandbox.paypal.com/v2/checkout/orders/ORDER-1",
        )

    def test_capture_order_success(self):
        self.mock_request.return_value = _response(
            201,
            {
                "id": "ORDER-1",
                "status": "COMPLETED",
                "purchase_units": [
                    {"payments": {"captures": [{"id": "CAPTURE-1", "status": "COMPLETED"}]}}
                ],
            },
        )
        result = self.client.capture_order("ORDER-1", request_id="capture-order-1")
        self.assertEqual(result["status"], "COMPLETED")

    def test_capture_order_provider_error_raises_order_exception(self):
        self.mock_request.return_value = _response(
            422, {"name": "UNPROCESSABLE_ENTITY", "message": "Order already captured"}
        )
        with self.assertRaises(PayPalOrderException) as ctx:
            self.client.capture_order("ORDER-1")
        self.assertEqual(ctx.exception.code, "UNPROCESSABLE_ENTITY")

    def test_refund_capture_full(self):
        self.mock_request.return_value = _response(201, {"id": "REFUND-1", "status": "COMPLETED"})
        result = self.client.refund_capture("CAPTURE-1", request_id="refund-1")
        self.assertEqual(result["id"], "REFUND-1")
        self.assertEqual(self.mock_request.call_args.kwargs["json"], {})

    def test_refund_capture_partial_includes_amount(self):
        self.mock_request.return_value = _response(201, {"id": "REFUND-1"})
        self.client.refund_capture("CAPTURE-1", amount="5.00", currency="USD")
        body = self.mock_request.call_args.kwargs["json"]
        self.assertEqual(body["amount"], {"currency_code": "USD", "value": "5.00"})

    def test_network_error_raises_provider_connection_exception(self):
        self.mock_request.side_effect = httpx.RequestError("boom")
        with self.assertRaises(ProviderConnectionException):
            self.client.get_order("ORDER-1")

    def test_timeout_raises_provider_connection_exception(self):
        self.mock_request.side_effect = httpx.TimeoutException("timed out")
        with self.assertRaises(ProviderConnectionException):
            self.client.get_order("ORDER-1")

    def test_non_json_error_body_handled_safely(self):
        self.mock_request.return_value = _response(500, ValueError("not json"))
        with self.assertRaises(PayPalOrderException):
            self.client.get_order("ORDER-1")


# ─── Subscriptions v1 ──────────────────────────────────────────────────


class SubscriptionsTests(_TokenCacheIsolationMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch("httpx.Client.post")
        self.mock_post = patcher.start()
        self.addCleanup(patcher.stop)
        request_patcher = patch(
            "httpx.Client.request"
        )
        self.mock_request = request_patcher.start()
        self.addCleanup(request_patcher.stop)
        self.mock_post.return_value = _valid_token_response()
        self.client = _client()

    def test_create_catalog_product(self):
        self.mock_request.return_value = _response(201, {"id": "PROD-1"})
        result = self.client.create_catalog_product(
            name="PocketLaw SaaS", request_id="catalog-product-pocketlaw"
        )
        self.assertEqual(result["id"], "PROD-1")

    def test_create_plan_monthly_pricing(self):
        self.mock_request.return_value = _response(201, {"id": "PLAN-1", "status": "ACTIVE"})
        result = self.client.create_plan(
            product_id="PROD-1",
            name="PocketLaw Pro (USD, monthly)",
            currency="USD",
            price="49.00",
            request_id="plan-pro-usd-monthly",
        )
        self.assertEqual(result["id"], "PLAN-1")
        body = self.mock_request.call_args.kwargs["json"]
        cycle = body["billing_cycles"][0]
        self.assertEqual(cycle["frequency"], {"interval_unit": "MONTH", "interval_count": 1})
        self.assertEqual(cycle["total_cycles"], 0)
        self.assertEqual(
            cycle["pricing_scheme"]["fixed_price"],
            {"value": "49.00", "currency_code": "USD"},
        )
        self.assertTrue(body["payment_preferences"]["auto_bill_outstanding"])

    def test_get_plan(self):
        self.mock_request.return_value = _response(200, {"id": "PLAN-1", "status": "ACTIVE"})
        result = self.client.get_plan("PLAN-1")
        self.assertEqual(result["status"], "ACTIVE")

    def test_create_subscription(self):
        self.mock_request.return_value = _response(201, {"id": "SUB-1", "status": "APPROVAL_PENDING"})
        result = self.client.create_subscription(plan_id="PLAN-1", custom_id="user-42")
        self.assertEqual(result["id"], "SUB-1")
        body = self.mock_request.call_args.kwargs["json"]
        self.assertEqual(body["custom_id"], "user-42")

    def test_get_subscription(self):
        self.mock_request.return_value = _response(200, {"id": "SUB-1", "status": "ACTIVE"})
        result = self.client.get_subscription("SUB-1")
        self.assertEqual(result["status"], "ACTIVE")

    def test_cancel_subscription_returns_none_on_204(self):
        self.mock_request.return_value = _response(204, {})
        result = self.client.cancel_subscription("SUB-1", reason="user requested")
        self.assertIsNone(result)

    def test_suspend_subscription(self):
        self.mock_request.return_value = _response(204, {})
        self.client.suspend_subscription("SUB-1", reason="payment failure policy")
        path = self.mock_request.call_args.args[1]
        self.assertTrue(path.endswith("/v1/billing/subscriptions/SUB-1/suspend"))

    def test_activate_subscription(self):
        self.mock_request.return_value = _response(204, {})
        self.client.activate_subscription("SUB-1")
        path = self.mock_request.call_args.args[1]
        self.assertTrue(path.endswith("/v1/billing/subscriptions/SUB-1/activate"))

    def test_revise_subscription(self):
        self.mock_request.return_value = _response(200, {"id": "SUB-1", "plan_id": "PLAN-2"})
        result = self.client.revise_subscription("SUB-1", plan_id="PLAN-2")
        self.assertEqual(result["plan_id"], "PLAN-2")

    def test_subscription_provider_error_raises_subscription_exception(self):
        self.mock_request.return_value = _response(
            404, {"name": "RESOURCE_NOT_FOUND", "message": "subscription not found"}
        )
        with self.assertRaises(PayPalSubscriptionException) as ctx:
            self.client.get_subscription("SUB-DOES-NOT-EXIST")
        self.assertEqual(ctx.exception.code, "RESOURCE_NOT_FOUND")


# ─── Webhook signature verification ────────────────────────────────────


_WEBHOOK_HEADERS = {
    "PAYPAL-AUTH-ALGO": "SHA256withRSA",
    "PAYPAL-CERT-URL": "https://api.paypal.com/cert/x",
    "PAYPAL-TRANSMISSION-ID": "abc-123",
    "PAYPAL-TRANSMISSION-SIG": "sig==",
    "PAYPAL-TRANSMISSION-TIME": "2026-01-01T00:00:00Z",
}
_WEBHOOK_EVENT = {"id": "WH-EVT-1", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {}}


class WebhookVerificationTests(_TokenCacheIsolationMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch("httpx.Client.post")
        self.mock_post = patcher.start()
        self.addCleanup(patcher.stop)
        request_patcher = patch(
            "httpx.Client.request"
        )
        self.mock_request = request_patcher.start()
        self.addCleanup(request_patcher.stop)
        self.mock_post.return_value = _valid_token_response()
        self.client = _client()

    def test_success_returns_true(self):
        self.mock_request.return_value = _response(200, {"verification_status": "SUCCESS"})
        self.assertTrue(
            self.client.verify_webhook_signature(
                headers=_WEBHOOK_HEADERS, raw_event=_WEBHOOK_EVENT
            )
        )
        body = self.mock_request.call_args.kwargs["json"]
        self.assertEqual(body["webhook_id"], "WH-TEST-1")
        self.assertEqual(body["webhook_event"], _WEBHOOK_EVENT)
        self.assertEqual(body["transmission_id"], "abc-123")

    def test_failure_status_raises(self):
        self.mock_request.return_value = _response(200, {"verification_status": "FAILURE"})
        with self.assertRaises(WebhookVerificationException):
            self.client.verify_webhook_signature(
                headers=_WEBHOOK_HEADERS, raw_event=_WEBHOOK_EVENT
            )

    def test_headers_are_matched_case_insensitively(self):
        lower_headers = {k.lower(): v for k, v in _WEBHOOK_HEADERS.items()}
        self.mock_request.return_value = _response(200, {"verification_status": "SUCCESS"})
        self.assertTrue(
            self.client.verify_webhook_signature(headers=lower_headers, raw_event=_WEBHOOK_EVENT)
        )

    def test_missing_header_raises_without_calling_paypal(self):
        incomplete = dict(_WEBHOOK_HEADERS)
        del incomplete["PAYPAL-TRANSMISSION-SIG"]
        with self.assertRaises(WebhookVerificationException):
            self.client.verify_webhook_signature(headers=incomplete, raw_event=_WEBHOOK_EVENT)
        self.mock_request.assert_not_called()

    def test_provider_http_error_raises_verification_exception(self):
        self.mock_request.return_value = _response(400, {"name": "VALIDATION_ERROR"})
        with self.assertRaises(WebhookVerificationException):
            self.client.verify_webhook_signature(
                headers=_WEBHOOK_HEADERS, raw_event=_WEBHOOK_EVENT
            )

    def test_network_error_raises_verification_exception_not_connection_exception(self):
        self.mock_request.side_effect = httpx.RequestError("boom")
        with self.assertRaises(WebhookVerificationException):
            self.client.verify_webhook_signature(
                headers=_WEBHOOK_HEADERS, raw_event=_WEBHOOK_EVENT
            )

    def test_uses_explicit_webhook_id_override(self):
        self.mock_request.return_value = _response(200, {"verification_status": "SUCCESS"})
        self.client.verify_webhook_signature(
            headers=_WEBHOOK_HEADERS, raw_event=_WEBHOOK_EVENT, webhook_id="WH-OVERRIDE"
        )
        body = self.mock_request.call_args.kwargs["json"]
        self.assertEqual(body["webhook_id"], "WH-OVERRIDE")
