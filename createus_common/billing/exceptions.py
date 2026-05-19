# filename: createus_common/billing/exceptions.py


class BillingException(Exception):
    """Base exception for all billing errors."""


class ProviderException(BillingException):
    """Raised when a payment provider returns an error response."""

    def __init__(self, message: str, code: str = "", raw: dict | None = None):
        self.code = code
        self.raw = raw or {}
        super().__init__(message)


class PaymentConfirmException(ProviderException):
    """Raised when payment confirmation fails at the provider."""


class PaymentCancelException(ProviderException):
    """Raised when payment cancellation fails at the provider."""


class ProviderConnectionException(BillingException):
    """Raised when a network-level error occurs communicating with a provider."""


class InsufficientCreditsException(BillingException):
    """Raised when a deduction exceeds available credit balance."""


class SubscriptionException(BillingException):
    """Raised for invalid subscription state transitions."""


class WebhookVerificationException(BillingException):
    """Raised when a webhook signature or payload fails verification."""
