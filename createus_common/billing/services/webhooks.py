# filename: createus_common/billing/services/webhooks.py

from __future__ import annotations

from typing import Any


class AbstractWebhookService:
    """
    Base class for provider webhook processing.

    Project apps subclass this per-provider and register handlers by
    event type via ``register_handler``.

    Example::

        class TossWebhookService(AbstractWebhookService):
            def verify(self, request):
                # signature check
                ...

        svc = TossWebhookService()
        svc.register_handler("PAYMENT_STATUS_CHANGED", handle_payment_changed)
        svc.process(event_type, payload)
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list] = {}

    def register_handler(self, event_type: str, handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def verify(self, request: Any) -> None:
        """Override to perform signature / authenticity verification."""
        raise NotImplementedError

    def process(self, event_type: str, payload: dict) -> None:
        """Dispatch payload to all handlers registered for event_type."""
        for handler in self._handlers.get(event_type, []):
            handler(payload)
