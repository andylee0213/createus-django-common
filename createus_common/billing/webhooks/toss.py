# filename: createus_common/billing/webhooks/toss.py

from __future__ import annotations

import json
from typing import Any

from createus_common.billing.exceptions import WebhookVerificationException
from createus_common.billing.services.webhooks import AbstractWebhookService

# TossPayments event types as of 2024
PAYMENT_STATUS_CHANGED = "PAYMENT_STATUS_CHANGED"
DEPOSIT_CALLBACK = "DEPOSIT_CALLBACK"


class TossWebhookHandler(AbstractWebhookService):
    """
    Parses and dispatches TossPayments webhook events.

    TossPayments currently does not sign webhook payloads with a secret —
    verification is done by checking the ``secret`` field in the body
    against a configured value.

    Usage in a DRF view::

        handler = TossWebhookHandler(webhook_secret="...")
        handler.register_handler(PAYMENT_STATUS_CHANGED, my_callback)

        # inside your view:
        handler.verify(request)
        event_type, payload = handler.parse(request)
        handler.process(event_type, payload)
    """

    def __init__(self, webhook_secret: str | None = None) -> None:
        super().__init__()
        self._webhook_secret = webhook_secret

    def verify(self, request: Any) -> None:
        """
        Validate the ``secret`` field embedded in the Toss webhook body.
        Raises :exc:`WebhookVerificationException` on mismatch.
        """
        if not self._webhook_secret:
            return

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError) as exc:
            raise WebhookVerificationException("Invalid webhook payload.") from exc

        if body.get("secret") != self._webhook_secret:
            raise WebhookVerificationException("Webhook secret mismatch.")

    def parse(self, request: Any) -> tuple[str, dict]:
        """
        Return ``(event_type, payload)`` from the raw request body.
        Raises :exc:`WebhookVerificationException` if the body is not valid JSON
        or is missing the ``eventType`` field.
        """
        try:
            body: dict = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError) as exc:
            raise WebhookVerificationException("Invalid webhook payload.") from exc

        event_type = body.get("eventType")
        if not event_type:
            raise WebhookVerificationException(
                "Webhook payload missing 'eventType' field."
            )
        return event_type, body
