# filename: createus_common/billing/providers/toss_payments.py

import base64

import httpx
from django.conf import settings

from createus_common.billing.exceptions import (
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
