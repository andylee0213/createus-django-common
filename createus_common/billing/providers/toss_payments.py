# filename: createus_common/billing/providers/toss_payments.py

import base64

import httpx
from django.conf import settings

from createus_common.billing.exceptions import (
    BillingKeyChargeException,
    BillingKeyIssueException,
    BillingKeyRevokeException,
    PaymentCancelException,
    PaymentConfirmException,
    ProviderConnectionException,
)

_TOSS_BASE_URL = "https://api.tosspayments.com/v1"


class TossPaymentsClient:
    """
    Thin wrapper around the TossPayments REST API.

    Usage::

        client = TossPaymentsClient()
        result = client.confirm_payment(payment_key, order_id, amount)

    ``secret_key`` can be injected directly for tests; otherwise it is read
    from ``settings.TOSS_PAYMENTS_SECRET_KEY`` at call time.
    """

    def __init__(self, secret_key: str | None = None) -> None:
        self._secret_key = secret_key

    def _resolve_secret_key(self) -> str:
        key = self._secret_key or getattr(settings, "TOSS_PAYMENTS_SECRET_KEY", None)
        if not key:
            raise ValueError(
                "TOSS_PAYMENTS_SECRET_KEY is not configured in Django settings."
            )
        return key

    def _auth_header(self) -> str:
        # TossPayments Basic auth: base64("{secret_key}:") — note the trailing colon
        token = base64.b64encode(f"{self._resolve_secret_key()}:".encode()).decode()
        return f"Basic {token}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
        }

    def confirm_payment(
        self,
        payment_key: str,
        order_id: str,
        amount: int,
    ) -> dict:
        """
        Call POST /v1/payments/confirm.

        Returns the full Toss Payment object on success.
        Raises :exc:`PaymentConfirmException` on provider error.
        Raises :exc:`ProviderConnectionException` on network failure.
        """
        url = f"{_TOSS_BASE_URL}/payments/confirm"
        payload = {
            "paymentKey": payment_key,
            "orderId": order_id,
            "amount": amount,
        }
        try:
            response = httpx.post(url, json=payload, headers=self._headers(), timeout=10)
        except httpx.RequestError as exc:
            raise ProviderConnectionException(
                "TossPayments request failed"
            ) from exc

        data: dict = response.json()
        if not response.is_success:
            raise PaymentConfirmException(
                message=data.get("message", "Payment confirmation failed"),
                code=data.get("code", "UNKNOWN"),
                raw=data,
            )
        return data

    def cancel_payment(
        self,
        payment_key: str,
        cancel_reason: str,
        cancel_amount: int | None = None,
        currency: str | None = None,
    ) -> dict:
        """
        Call POST /v1/payments/{paymentKey}/cancel.

        ``cancel_amount`` omitted → full cancellation.
        ``currency`` required by Toss for partial foreign-currency cancellations.

        Returns the updated Toss Payment object on success.
        Raises :exc:`PaymentCancelException` on provider error.
        Raises :exc:`ProviderConnectionException` on network failure.
        """
        url = f"{_TOSS_BASE_URL}/payments/{payment_key}/cancel"
        payload: dict = {"cancelReason": cancel_reason}
        if cancel_amount is not None:
            payload["cancelAmount"] = cancel_amount
        if currency is not None:
            payload["currency"] = currency

        try:
            response = httpx.post(url, json=payload, headers=self._headers(), timeout=10)
        except httpx.RequestError as exc:
            raise ProviderConnectionException(
                "TossPayments request failed"
            ) from exc

        data: dict = response.json()
        if not response.is_success:
            raise PaymentCancelException(
                message=data.get("message", "Payment cancellation failed"),
                code=data.get("code", "UNKNOWN"),
                raw=data,
            )
        return data

    def issue_billing_key(self, auth_key: str, customer_key: str) -> dict:
        """
        Exchange a frontend-issued ``authKey`` for a persistent ``billingKey``.

        Call this from the ``billing-success`` redirect handler after the user
        completes ``requestBillingAuth()`` in the Toss SDK.

        Endpoint: POST /v1/billing/authorizations/issue

        Returns the full Toss billing authorizations object on success.
        The ``billingKey`` in the response is sensitive — callers must store
        it securely (encrypted at rest) and must not log it.

        Raises :exc:`BillingKeyIssueException` on provider error.
        Raises :exc:`ProviderConnectionException` on network failure.
        """
        url = f"{_TOSS_BASE_URL}/billing/authorizations/issue"
        payload = {
            "authKey": auth_key,
            "customerKey": customer_key,
        }
        try:
            response = httpx.post(url, json=payload, headers=self._headers(), timeout=10)
        except httpx.RequestError as exc:
            raise ProviderConnectionException(
                "TossPayments billing authorizations request failed"
            ) from exc

        data: dict = response.json()
        if not response.is_success:
            raise BillingKeyIssueException(
                message=data.get("message", "Billing key issuance failed"),
                code=data.get("code", "UNKNOWN"),
                raw=data,
            )
        return data

    def charge_billing_key(
        self,
        billing_key: str,
        customer_key: str,
        amount: int,
        order_id: str,
        order_name: str,
        customer_email: str | None = None,
        customer_name: str | None = None,
        customer_ip: str | None = None,
        tax_free_amount: int = 0,
        tax_exemption_amount: int = 0,
    ) -> dict:
        """
        Charge a stored ``billingKey`` for automatic (recurring) payment.

        Endpoint: POST /v1/billing/{billingKey}

        ``customer_email``, ``customer_name``, and ``customer_ip`` are included
        in the request body only when provided.  ``tax_free_amount`` and
        ``tax_exemption_amount`` default to 0 per Toss requirements.

        Timeout is 60 seconds — Toss states that billing approval can take up
        to 60 seconds for some card issuers.

        The ``billingKey`` is never written to exception messages to avoid
        leaking credentials in logs.

        Returns the full Toss payment object on success.
        Raises :exc:`BillingKeyChargeException` on provider error.
        Raises :exc:`ProviderConnectionException` on network failure.
        """
        url = f"{_TOSS_BASE_URL}/billing/{billing_key}"
        payload: dict = {
            "customerKey": customer_key,
            "amount": amount,
            "orderId": order_id,
            "orderName": order_name,
            "taxFreeAmount": tax_free_amount,
            "taxExemptionAmount": tax_exemption_amount,
        }
        if customer_email is not None:
            payload["customerEmail"] = customer_email
        if customer_name is not None:
            payload["customerName"] = customer_name
        if customer_ip is not None:
            payload["customerIp"] = customer_ip

        try:
            response = httpx.post(url, json=payload, headers=self._headers(), timeout=60)
        except httpx.RequestError as exc:
            raise ProviderConnectionException(
                "TossPayments billing charge request failed"
            ) from exc

        data: dict = response.json()
        if not response.is_success:
            raise BillingKeyChargeException(
                message=data.get("message", "Billing charge failed"),
                code=data.get("code", "UNKNOWN"),
                raw=data,
            )
        return data

    def revoke_billing_key(self, billing_key: str) -> None:
        """
        Revoke (delete) a stored ``billingKey`` at the provider.

        Endpoint: DELETE /v1/billing/{billingKey}

        Expected response: HTTP 200 with an empty body.  Call this when a user
        cancels their subscription or requests card removal.  After revocation
        the billingKey cannot be used for further charges.

        The ``billingKey`` is never written to exception messages to avoid
        leaking credentials in logs.

        Returns ``None`` on success.
        Raises :exc:`BillingKeyRevokeException` on provider error.
        Raises :exc:`ProviderConnectionException` on network failure.
        """
        url = f"{_TOSS_BASE_URL}/billing/{billing_key}"
        try:
            response = httpx.delete(url, headers=self._headers(), timeout=10)
        except httpx.RequestError as exc:
            raise ProviderConnectionException(
                "TossPayments billing revoke request failed"
            ) from exc

        if not response.is_success:
            try:
                data: dict = response.json()
            except Exception:
                data = {}
            raise BillingKeyRevokeException(
                message=data.get("message", "Billing key revocation failed"),
                code=data.get("code", "UNKNOWN"),
                raw=data,
            )
        return None
