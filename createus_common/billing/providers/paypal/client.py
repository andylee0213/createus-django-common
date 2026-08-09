# filename: createus_common/billing/providers/paypal/client.py

"""
Thin wrapper around the PayPal REST API (Orders v2, Subscriptions v1,
Webhooks) built on ``httpx``.

Design notes
------------
- Every network call has a strict timeout; nothing blocks indefinitely.
- Every non-2xx response raises a typed exception from
  ``createus_common.billing.exceptions`` whose message never contains the
  raw response body verbatim (only the provider's own ``message``/``name``
  fields, which PayPal does not populate with secrets) and never contains
  the access token or client secret.
- The OAuth2 access token is cached in-process (per Python process, keyed by
  mode + client id) with an expiry safety margin, so a burst of requests
  does not each pay the token round trip; nothing about the token is ever
  logged.
- All requests go through one process-wide, keep-alive ``httpx.Client``
  (see ``_get_http_client()``) instead of the ``httpx.post``/``httpx.request``
  module-level convenience functions, which each open and tear down a fresh
  TCP+TLS connection per call. Reusing connections matters here specifically
  because a buyer-facing flow (e.g. the PayPal Buttons popup opening blank
  while ``createOrder`` resolves) is directly exposed to this latency —
  every checkout previously paid a full handshake for the token call *and*
  a second one for the order/capture call, even with a cached token.
- All mutating POST calls accept an optional ``request_id`` which is sent as
  the ``PayPal-Request-Id`` header — PayPal's documented idempotency
  mechanism for Orders and Subscriptions APIs. Callers should pass a
  deterministic value (e.g. derived from the local order/purchase id) so a
  retried request cannot create a duplicate order/plan/subscription at
  PayPal.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from createus_common.billing.exceptions import (
    PayPalAuthException,
    PayPalOrderException,
    PayPalSubscriptionException,
    ProviderConnectionException,
    WebhookVerificationException,
)
from createus_common.billing.providers.paypal import conf as paypal_conf

# Refresh the cached token this many seconds before it actually expires, so
# a request that starts just before expiry never races against PayPal
# invalidating the token mid-flight.
_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 60

# In-process token cache: {"{mode}:{client_id}": (access_token, expires_at_monotonic)}
# Deliberately process-local (not Redis/DB) — a wasted extra token fetch per
# worker process on cold start is a fair trade for not needing a shared
# cache dependency in a library used by multiple projects.
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_TOKEN_CACHE_LOCK = threading.Lock()

# One process-wide httpx.Client, created lazily on first use and reused for
# every call this library ever makes (sandbox and live are different hosts,
# but a single Client pools connections per-host internally, so one instance
# correctly serves both). httpx.Client is documented thread-safe for
# concurrent requests, matching a threaded WSGI worker's usage pattern.
# Tests patch httpx.Client.post/.request at the class level rather than this
# singleton directly, so they don't need to know about its lifecycle.
_http_client: httpx.Client | None = None
_HTTP_CLIENT_LOCK = threading.Lock()


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        with _HTTP_CLIENT_LOCK:
            if _http_client is None:
                _http_client = httpx.Client()
    return _http_client

# Required headers PayPal sends with every webhook delivery, used verbatim
# in the verify-webhook-signature call. Keys are matched case-insensitively
# against whatever the caller passes in (Django's HttpRequest.headers is
# already case-insensitive, but a caller may pass a plain dict).
_REQUIRED_WEBHOOK_HEADERS = (
    "PAYPAL-AUTH-ALGO",
    "PAYPAL-CERT-URL",
    "PAYPAL-TRANSMISSION-ID",
    "PAYPAL-TRANSMISSION-SIG",
    "PAYPAL-TRANSMISSION-TIME",
)


def _safe_error_message(data: dict, fallback: str) -> str:
    """
    Extract a human-readable message from a PayPal error body without ever
    forwarding the full body (which could, in principle, echo back
    caller-supplied fields) into an exception string/log line.
    """
    message = data.get("message") or data.get("name") or fallback
    return str(message)[:500]


def _sanitized_raw(data: dict) -> dict:
    """
    PayPal error/response bodies do not contain secrets, but defensively
    strip anything that looks like one before it is ever attached to an
    exception (which application code may log).
    """
    if not isinstance(data, dict):
        return {}
    redacted = {}
    for key, value in data.items():
        lowered = key.lower()
        if "secret" in lowered or "token" in lowered or "authorization" in lowered:
            redacted[key] = "***redacted***"
        else:
            redacted[key] = value
    return redacted


class PayPalClient:
    """
    Usage::

        client = PayPalClient()                    # reads Django settings
        order = client.create_order(
            amount="49.00", currency="USD",
            reference_id=purchase.order_id, request_id=purchase.order_id,
        )

    ``mode``/``client_id``/``client_secret``/``webhook_id`` can be injected
    directly (mainly for tests); otherwise they are resolved from Django
    settings via :mod:`createus_common.billing.providers.paypal.conf` at
    call time so a client instance created before settings finish loading
    still works correctly.
    """

    def __init__(
        self,
        *,
        mode: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        webhook_id: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._mode = mode or paypal_conf.get_mode()
        self._client_id = client_id or paypal_conf.get_client_id()
        self._client_secret = client_secret or paypal_conf.get_client_secret()
        self._webhook_id = webhook_id
        self._base_url = paypal_conf.get_base_url(self._mode)
        self._timeout = timeout

    # ── OAuth2 ───────────────────────────────────────────────────────────

    def _token_cache_key(self) -> str:
        return f"{self._mode}:{self._client_id}"

    def _get_access_token(self) -> str:
        cache_key = self._token_cache_key()
        cached = _TOKEN_CACHE.get(cache_key)
        now = time.monotonic()
        if cached and cached[1] - _TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS > now:
            return cached[0]

        with _TOKEN_CACHE_LOCK:
            # Re-check inside the lock — another thread may have refreshed
            # the token while this one was waiting.
            cached = _TOKEN_CACHE.get(cache_key)
            now = time.monotonic()
            if cached and cached[1] - _TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS > now:
                return cached[0]

            token, expires_in = self._fetch_access_token()
            _TOKEN_CACHE[cache_key] = (token, time.monotonic() + expires_in)
            return token

    def _fetch_access_token(self) -> tuple[str, int]:
        url = f"{self._base_url}/v1/oauth2/token"
        try:
            response = _get_http_client().post(
                url,
                data={"grant_type": "client_credentials"},
                auth=(self._client_id, self._client_secret),
                headers={"Accept": "application/json"},
                timeout=self._timeout,
            )
        except httpx.RequestError as exc:
            raise ProviderConnectionException(
                "PayPal OAuth2 token request failed"
            ) from exc

        try:
            data = response.json()
        except ValueError:
            data = {}

        if not response.is_success:
            raise PayPalAuthException(
                message=_safe_error_message(data, "PayPal token request failed"),
                code=str(data.get("error", "UNKNOWN")),
                raw=_sanitized_raw(data),
            )

        access_token = data.get("access_token")
        expires_in = data.get("expires_in")
        if not access_token or not isinstance(expires_in, int):
            raise PayPalAuthException(
                message="PayPal token response missing access_token/expires_in",
                code="MALFORMED_TOKEN_RESPONSE",
                raw={},
            )
        return access_token, expires_in

    # ── Internal request helper ─────────────────────────────────────────

    def _headers(self, *, request_id: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        exception_cls: type,
        json_body: dict | None = None,
        request_id: str | None = None,
        expected_statuses: tuple[int, ...] = (200, 201),
    ) -> dict:
        url = f"{self._base_url}{path}"
        try:
            response = _get_http_client().request(
                method,
                url,
                json=json_body,
                headers=self._headers(request_id=request_id),
                timeout=self._timeout,
            )
        except httpx.RequestError as exc:
            raise ProviderConnectionException(
                f"PayPal request failed: {method} {path}"
            ) from exc

        if response.status_code == 204:
            return {}

        try:
            data = response.json()
        except ValueError:
            data = {}

        if response.status_code not in expected_statuses:
            raise exception_cls(
                message=_safe_error_message(data, f"PayPal request failed: {method} {path}"),
                code=str(data.get("name", "UNKNOWN")),
                raw=_sanitized_raw(data),
            )
        return data

    # ── Orders v2 ────────────────────────────────────────────────────────

    def create_order(
        self,
        *,
        amount: str,
        currency: str,
        reference_id: str,
        custom_id: str = "",
        description: str = "",
        request_id: str | None = None,
        return_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict:
        """
        POST /v2/checkout/orders — CAPTURE-intent order for exactly one
        purchase unit. ``amount`` must be a decimal string ("49.00"), never
        a float, to avoid binary-float rounding drift.
        """
        purchase_unit: dict[str, Any] = {
            "reference_id": reference_id,
            "amount": {"currency_code": currency, "value": amount},
        }
        if custom_id:
            purchase_unit["custom_id"] = custom_id
        if description:
            purchase_unit["description"] = description[:127]

        body: dict[str, Any] = {
            "intent": "CAPTURE",
            "purchase_units": [purchase_unit],
        }
        if return_url or cancel_url:
            body["application_context"] = {
                k: v
                for k, v in {
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                    "user_action": "PAY_NOW",
                }.items()
                if v
            }

        return self._request(
            "POST",
            "/v2/checkout/orders",
            exception_cls=PayPalOrderException,
            json_body=body,
            request_id=request_id,
            expected_statuses=(200, 201),
        )

    def get_order(self, order_id: str) -> dict:
        """GET /v2/checkout/orders/{id} — authoritative order state."""
        return self._request(
            "GET",
            f"/v2/checkout/orders/{order_id}",
            exception_cls=PayPalOrderException,
        )

    def capture_order(self, order_id: str, *, request_id: str | None = None) -> dict:
        """
        POST /v2/checkout/orders/{id}/capture.

        Idempotent at PayPal's end when ``request_id`` is supplied: a retry
        with the same ``PayPal-Request-Id`` returns the original capture
        result instead of creating a second capture.
        """
        return self._request(
            "POST",
            f"/v2/checkout/orders/{order_id}/capture",
            exception_cls=PayPalOrderException,
            json_body={},
            request_id=request_id,
            expected_statuses=(200, 201),
        )

    def refund_capture(
        self,
        capture_id: str,
        *,
        amount: str | None = None,
        currency: str | None = None,
        note: str = "",
        request_id: str | None = None,
    ) -> dict:
        """
        POST /v2/payments/captures/{id}/refund.

        Omit ``amount``/``currency`` for a full refund of the capture.
        """
        body: dict[str, Any] = {}
        if amount is not None and currency is not None:
            body["amount"] = {"currency_code": currency, "value": amount}
        if note:
            body["note_to_payer"] = note[:255]

        return self._request(
            "POST",
            f"/v2/payments/captures/{capture_id}/refund",
            exception_cls=PayPalOrderException,
            json_body=body,
            request_id=request_id,
            expected_statuses=(200, 201),
        )

    # ── Subscriptions v1 ─────────────────────────────────────────────────

    def create_catalog_product(
        self,
        *,
        name: str,
        description: str = "",
        product_type: str = "SERVICE",
        category: str = "SOFTWARE",
        request_id: str | None = None,
    ) -> dict:
        """POST /v1/catalogs/products — one catalog product per SaaS offering."""
        body = {
            "name": name,
            "type": product_type,
            "category": category,
        }
        if description:
            body["description"] = description[:256]
        return self._request(
            "POST",
            "/v1/catalogs/products",
            exception_cls=PayPalSubscriptionException,
            json_body=body,
            request_id=request_id,
            expected_statuses=(200, 201),
        )

    def create_plan(
        self,
        *,
        product_id: str,
        name: str,
        currency: str,
        price: str,
        description: str = "",
        interval_unit: str = "MONTH",
        interval_count: int = 1,
        request_id: str | None = None,
    ) -> dict:
        """
        POST /v1/billing/plans — a single regular pricing cycle that repeats
        indefinitely (``total_cycles: 0``), auto-billing outstanding amounts
        on the next cycle if a charge fails so a single failed payment does
        not by itself cancel the subscription.
        """
        body = {
            "product_id": product_id,
            "name": name,
            "billing_cycles": [
                {
                    "frequency": {
                        "interval_unit": interval_unit,
                        "interval_count": interval_count,
                    },
                    "tenure_type": "REGULAR",
                    "sequence": 1,
                    "total_cycles": 0,
                    "pricing_scheme": {
                        "fixed_price": {"value": price, "currency_code": currency}
                    },
                }
            ],
            "payment_preferences": {
                "auto_bill_outstanding": True,
                "payment_failure_threshold": 3,
            },
        }
        if description:
            body["description"] = description[:127]
        return self._request(
            "POST",
            "/v1/billing/plans",
            exception_cls=PayPalSubscriptionException,
            json_body=body,
            request_id=request_id,
            expected_statuses=(200, 201),
        )

    def get_plan(self, plan_id: str) -> dict:
        """GET /v1/billing/plans/{id}."""
        return self._request(
            "GET",
            f"/v1/billing/plans/{plan_id}",
            exception_cls=PayPalSubscriptionException,
        )

    def create_subscription(
        self,
        *,
        plan_id: str,
        custom_id: str = "",
        subscriber: dict | None = None,
        request_id: str | None = None,
    ) -> dict:
        """
        POST /v1/billing/subscriptions — server-side subscription creation.

        Not used by the standard browser PayPal-button flow (the JS SDK
        creates the subscription client-side from the plan id and returns
        the resulting subscription id for the server to verify), but
        provided for flows that need to originate the subscription
        server-side.
        """
        body: dict[str, Any] = {"plan_id": plan_id}
        if custom_id:
            body["custom_id"] = custom_id
        if subscriber:
            body["subscriber"] = subscriber
        return self._request(
            "POST",
            "/v1/billing/subscriptions",
            exception_cls=PayPalSubscriptionException,
            json_body=body,
            request_id=request_id,
            expected_statuses=(200, 201),
        )

    def get_subscription(self, subscription_id: str) -> dict:
        """GET /v1/billing/subscriptions/{id} — authoritative subscription state."""
        return self._request(
            "GET",
            f"/v1/billing/subscriptions/{subscription_id}",
            exception_cls=PayPalSubscriptionException,
        )

    def cancel_subscription(
        self, subscription_id: str, *, reason: str = "", request_id: str | None = None
    ) -> None:
        """POST /v1/billing/subscriptions/{id}/cancel — returns 204 No Content."""
        self._request(
            "POST",
            f"/v1/billing/subscriptions/{subscription_id}/cancel",
            exception_cls=PayPalSubscriptionException,
            json_body={"reason": reason[:128]} if reason else {},
            request_id=request_id,
            expected_statuses=(204,),
        )

    def suspend_subscription(
        self, subscription_id: str, *, reason: str = "", request_id: str | None = None
    ) -> None:
        """POST /v1/billing/subscriptions/{id}/suspend — returns 204 No Content."""
        self._request(
            "POST",
            f"/v1/billing/subscriptions/{subscription_id}/suspend",
            exception_cls=PayPalSubscriptionException,
            json_body={"reason": reason[:128]} if reason else {},
            request_id=request_id,
            expected_statuses=(204,),
        )

    def activate_subscription(
        self, subscription_id: str, *, reason: str = "", request_id: str | None = None
    ) -> None:
        """POST /v1/billing/subscriptions/{id}/activate — returns 204 No Content."""
        self._request(
            "POST",
            f"/v1/billing/subscriptions/{subscription_id}/activate",
            exception_cls=PayPalSubscriptionException,
            json_body={"reason": reason[:128]} if reason else {},
            request_id=request_id,
            expected_statuses=(204,),
        )

    def revise_subscription(
        self, subscription_id: str, *, plan_id: str, request_id: str | None = None
    ) -> dict:
        """POST /v1/billing/subscriptions/{id}/revise — plan upgrade/downgrade."""
        return self._request(
            "POST",
            f"/v1/billing/subscriptions/{subscription_id}/revise",
            exception_cls=PayPalSubscriptionException,
            json_body={"plan_id": plan_id},
            request_id=request_id,
            expected_statuses=(200,),
        )

    # ── Webhooks ─────────────────────────────────────────────────────────

    def verify_webhook_signature(
        self,
        *,
        headers: dict[str, str],
        raw_event: dict,
        webhook_id: str | None = None,
    ) -> bool:
        """
        POST /v1/notifications/verify-webhook-signature.

        ``headers`` must contain (case-insensitively) the five
        ``PAYPAL-*`` transmission headers PayPal sends with every webhook
        delivery; ``raw_event`` is the exact parsed JSON body PayPal sent.

        Returns ``True`` only when PayPal reports
        ``verification_status == "SUCCESS"``. Raises
        :exc:`WebhookVerificationException` for missing headers, transport
        failures, or any other verification status (including PayPal
        returning an error) — callers must treat every non-``True`` outcome
        as "reject the request", never as "assume valid".
        """
        normalized = {k.upper(): v for k, v in headers.items()}
        missing = [h for h in _REQUIRED_WEBHOOK_HEADERS if not normalized.get(h)]
        if missing:
            raise WebhookVerificationException(
                f"Missing required PayPal webhook headers: {', '.join(missing)}"
            )

        resolved_webhook_id = webhook_id or self._webhook_id or paypal_conf.get_webhook_id()

        body = {
            "auth_algo": normalized["PAYPAL-AUTH-ALGO"],
            "cert_url": normalized["PAYPAL-CERT-URL"],
            "transmission_id": normalized["PAYPAL-TRANSMISSION-ID"],
            "transmission_sig": normalized["PAYPAL-TRANSMISSION-SIG"],
            "transmission_time": normalized["PAYPAL-TRANSMISSION-TIME"],
            "webhook_id": resolved_webhook_id,
            "webhook_event": raw_event,
        }

        try:
            data = self._request(
                "POST",
                "/v1/notifications/verify-webhook-signature",
                exception_cls=WebhookVerificationException,
                json_body=body,
                expected_statuses=(200,),
            )
        except WebhookVerificationException:
            raise
        except ProviderConnectionException:
            raise WebhookVerificationException(
                "Could not reach PayPal to verify webhook signature"
            )

        status = data.get("verification_status")
        if status != "SUCCESS":
            raise WebhookVerificationException(
                f"PayPal webhook signature verification status was {status!r}, not SUCCESS"
            )
        return True
