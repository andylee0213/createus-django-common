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


class WebhookVerificationException(ProviderException):
    """
    Raised when a webhook signature or payload fails verification.

    Subclasses ``ProviderException`` (not just ``BillingException``) so
    provider clients that call PayPal's ``verify-webhook-signature`` API can
    raise it the same way they raise every other provider error — with an
    optional ``code``/``raw`` — while every existing call site that raises
    it with only a message (``WebhookVerificationException("...")``, as
    ``createus_common.billing.webhooks.toss`` does) keeps working unchanged.
    """


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


class PayPalAuthException(ProviderException):
    """Raised when PayPal OAuth2 client-credentials token retrieval fails."""


class PayPalOrderException(ProviderException):
    """Raised when a PayPal Orders v2 API call (create/get/capture/refund) fails."""


class PayPalSubscriptionException(ProviderException):
    """Raised when a PayPal Subscriptions v1 API call fails."""
