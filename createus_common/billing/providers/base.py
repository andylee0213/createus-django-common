# filename: createus_common/billing/providers/base.py

"""
Provider-agnostic contract for app-store style recurring purchase backends.

``createus_common.billing.providers.apple`` implements this interface today.
A future ``createus_common.billing.providers.google`` package (Google Play
Developer API + Real-time Developer Notifications) implements the same
interface, so ``createus_common.billing.services.entitlement`` and the DRF
views never need to know which store they are talking to — they only ever
see the dataclasses defined here.

Nothing in this module imports Django or any store-specific SDK; it is pure
Python so it can be unit tested without a configured Django project.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum


class StoreSubscriptionState(IntEnum):
    """
    Normalized subscription state as reported by the store's authoritative
    API — deliberately store-agnostic wording (no "billing retry" vs
    "on hold" naming disputes between Apple and Google).

    Numeric values are stable and referenced by
    ``createus_common.billing.services.entitlement``; do not renumber.
    """

    ACTIVE = 1
    EXPIRED = 2
    BILLING_RETRY = 3
    GRACE_PERIOD = 4
    REVOKED = 5


@dataclass(frozen=True)
class NormalizedTransaction:
    """A single verified purchase/renewal event, store-agnostic shape."""

    provider: int  # createus_common.billing.choices.PaymentProvider value
    environment: str  # "sandbox" | "production"
    original_transaction_id: str
    transaction_id: str
    product_id: str
    purchase_date: datetime | None
    original_purchase_date: datetime | None
    expires_date: datetime | None
    quantity: int
    transaction_type: str
    in_app_ownership_type: str
    subscription_group_id: str
    offer_type: int | None
    offer_identifier: str
    revocation_date: datetime | None
    revocation_reason: int | None
    is_upgraded: bool
    transaction_reason: str
    storefront: str
    storefront_id: str
    price: int | None
    currency: str
    signed_transaction_info: str = ""
    raw: dict = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class NormalizedRenewalInfo:
    """Store-agnostic renewal/auto-renew intent, decoded from renewal info."""

    original_transaction_id: str
    auto_renew_product_id: str
    auto_renew_status: bool | None
    expiration_intent: int | None
    grace_period_expires_date: datetime | None
    is_in_billing_retry_period: bool | None
    price_increase_status: int | None
    environment: str
    renewal_date: datetime | None
    renewal_price: int | None
    currency: str
    signed_renewal_info: str = ""
    raw: dict = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class SubscriptionStatusSnapshot:
    """One entry of a store's "current status of this subscription" answer."""

    state: StoreSubscriptionState
    transaction: NormalizedTransaction | None
    renewal_info: NormalizedRenewalInfo | None


@dataclass(frozen=True)
class NormalizedNotification:
    """A verified server-to-server notification, store-agnostic shape."""

    provider: int
    notification_uuid: str
    notification_type: str
    subtype: str
    environment: str
    transaction: NormalizedTransaction | None
    renewal_info: NormalizedRenewalInfo | None
    state: StoreSubscriptionState | None
    raw: dict = field(default_factory=dict, repr=False)


class AbstractStoreProvider(ABC):
    """
    Provider-agnostic interface the entitlement engine and views depend on.

    Every method either returns verified, normalized data or raises —
    there is no "trust me" code path. Implementations must perform
    cryptographic verification (or, for APIs, authenticated server-to-server
    calls) before returning anything to the caller.
    """

    #: createus_common.billing.choices.PaymentProvider value, set by subclass.
    provider_id: int

    @abstractmethod
    def verify_and_decode_transaction(self, signed_transaction: str) -> NormalizedTransaction:
        """Cryptographically verify and decode a signed transaction payload."""

    @abstractmethod
    def verify_and_decode_renewal_info(self, signed_renewal_info: str) -> NormalizedRenewalInfo:
        """Cryptographically verify and decode a signed renewal-info payload."""

    @abstractmethod
    def verify_and_decode_notification(self, signed_payload: str) -> NormalizedNotification:
        """Cryptographically verify and decode a server notification payload."""

    @abstractmethod
    def get_subscription_statuses(
        self, original_transaction_id: str
    ) -> list[SubscriptionStatusSnapshot]:
        """
        Ask the store's server-to-server API for the current, authoritative
        status of every subscription in the group ``original_transaction_id``
        belongs to. This is the call that makes client-submitted data
        untrustable-by-itself irrelevant: whatever the client claims, this
        is what actually gets granted.
        """
