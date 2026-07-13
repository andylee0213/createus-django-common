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


class BillingKeyIssueException(ProviderException):
    """Raised when exchanging an authKey for a billingKey fails at the provider."""


class BillingKeyChargeException(ProviderException):
    """Raised when charging a stored billingKey fails at the provider."""


class BillingKeyRevokeException(ProviderException):
    """Raised when revoking a billingKey fails at the provider."""


class WebhookVerificationException(BillingException):
    """Raised when a webhook signature or payload fails verification."""


class TransactionVerificationException(BillingException):
    """
    Raised when a store-signed transaction, renewal info, or notification
    payload (e.g. Apple's JWS) fails cryptographic verification — bad
    signature, untrusted certificate chain, wrong bundle id, or wrong
    environment.

    Callers must treat this as "reject the request" (HTTP 400), never as
    "fall back to trusting the client's claim."
    """


class StoreAPIException(ProviderException):
    """
    Raised when a store server API (App Store Server API, Google Play
    Developer API) returns an error response for an authenticated,
    server-to-server call.
    """
