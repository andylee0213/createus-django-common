# filename: createus_common/billing/providers/apple/mapping.py

"""
Pure functions converting Apple's ``app-store-server-library`` decoded
objects (attrs instances with camelCase field names, matching Apple's JSON
schema) into this package's store-agnostic normalized dataclasses and
JSON-safe dicts.

Kept separate from ``client.py`` so the conversion logic can be unit tested
without constructing a real ``AppleAppStoreProvider`` (no settings, no
network, no cryptography).
"""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from enum import Enum
from typing import Any

import attr

from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.models.Status import Status

from createus_common.billing.choices import PaymentProvider
from createus_common.billing.providers.base import (
    NormalizedNotification,
    NormalizedRenewalInfo,
    NormalizedTransaction,
    StoreSubscriptionState,
)

_STATUS_TO_STATE: dict[Status, StoreSubscriptionState] = {
    Status.ACTIVE: StoreSubscriptionState.ACTIVE,
    Status.EXPIRED: StoreSubscriptionState.EXPIRED,
    Status.BILLING_RETRY: StoreSubscriptionState.BILLING_RETRY,
    Status.BILLING_GRACE_PERIOD: StoreSubscriptionState.GRACE_PERIOD,
    Status.REVOKED: StoreSubscriptionState.REVOKED,
}


def status_to_state(status: Status | None) -> StoreSubscriptionState | None:
    if status is None:
        return None
    return _STATUS_TO_STATE.get(status)


def _ms_to_datetime(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=dt_timezone.utc)


def _environment_to_str(value: Environment | None) -> str:
    if value == Environment.SANDBOX:
        return "sandbox"
    if value == Environment.PRODUCTION:
        return "production"
    if value is None:
        return ""
    # Xcode / LocalTesting fall through here — surfaced verbatim rather than
    # silently coerced, since a subscription created in those environments
    # should never reach production entitlement logic.
    return str(getattr(value, "value", value)).lower()


def _enum_safe(_inst: Any, _field: Any, value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def serialize_attrs(obj: Any) -> dict:
    """Recursively convert an attrs-decoded Apple payload into a JSON-safe dict."""
    if obj is None:
        return {}
    return attr.asdict(obj, recurse=True, value_serializer=_enum_safe)


def decode_transaction_to_normalized(decoded) -> NormalizedTransaction:
    return NormalizedTransaction(
        provider=PaymentProvider.APP_STORE,
        environment=_environment_to_str(decoded.environment),
        original_transaction_id=decoded.originalTransactionId or "",
        transaction_id=decoded.transactionId or "",
        product_id=decoded.productId or "",
        purchase_date=_ms_to_datetime(decoded.purchaseDate),
        original_purchase_date=_ms_to_datetime(decoded.originalPurchaseDate),
        expires_date=_ms_to_datetime(decoded.expiresDate),
        quantity=decoded.quantity if decoded.quantity is not None else 1,
        transaction_type=decoded.type.value if decoded.type else "",
        in_app_ownership_type=(
            decoded.inAppOwnershipType.value if decoded.inAppOwnershipType else ""
        ),
        subscription_group_id=decoded.subscriptionGroupIdentifier or "",
        offer_type=int(decoded.offerType) if decoded.offerType is not None else None,
        offer_identifier=decoded.offerIdentifier or "",
        revocation_date=_ms_to_datetime(decoded.revocationDate),
        revocation_reason=(
            int(decoded.revocationReason) if decoded.revocationReason is not None else None
        ),
        is_upgraded=bool(decoded.isUpgraded),
        transaction_reason=(
            decoded.transactionReason.value if decoded.transactionReason else ""
        ),
        storefront=decoded.storefront or "",
        storefront_id=decoded.storefrontId or "",
        price=decoded.price,
        currency=decoded.currency or "",
        raw=serialize_attrs(decoded),
    )


def decode_renewal_info_to_normalized(decoded) -> NormalizedRenewalInfo:
    return NormalizedRenewalInfo(
        original_transaction_id=decoded.originalTransactionId or "",
        auto_renew_product_id=decoded.autoRenewProductId or "",
        auto_renew_status=(
            bool(int(decoded.autoRenewStatus)) if decoded.autoRenewStatus is not None else None
        ),
        expiration_intent=(
            int(decoded.expirationIntent) if decoded.expirationIntent is not None else None
        ),
        grace_period_expires_date=_ms_to_datetime(decoded.gracePeriodExpiresDate),
        is_in_billing_retry_period=decoded.isInBillingRetryPeriod,
        price_increase_status=(
            int(decoded.priceIncreaseStatus) if decoded.priceIncreaseStatus is not None else None
        ),
        environment=_environment_to_str(decoded.environment),
        renewal_date=_ms_to_datetime(decoded.renewalDate),
        renewal_price=decoded.renewalPrice,
        currency=decoded.currency or "",
        raw=serialize_attrs(decoded),
    )


def decode_notification_to_normalized(decoded, provider) -> NormalizedNotification:
    """
    ``provider`` is the ``AppleAppStoreProvider`` instance doing the
    decoding, passed in so nested ``signedTransactionInfo`` /
    ``signedRenewalInfo`` JWS strings can be verified with the same
    ``SignedDataVerifier`` rather than trusted un-checked just because they
    arrived inside an outer, already-verified envelope.
    """
    data = decoded.data
    transaction = None
    renewal_info = None
    state = None

    if data is not None:
        if data.signedTransactionInfo:
            transaction = provider.verify_and_decode_transaction(data.signedTransactionInfo)
        if data.signedRenewalInfo:
            renewal_info = provider.verify_and_decode_renewal_info(data.signedRenewalInfo)
        state = status_to_state(data.status)
        environment = _environment_to_str(data.environment)
    else:
        environment = ""

    return NormalizedNotification(
        provider=PaymentProvider.APP_STORE,
        notification_uuid=decoded.notificationUUID or "",
        notification_type=decoded.notificationType.value if decoded.notificationType else "",
        subtype=decoded.subtype.value if decoded.subtype else "",
        environment=environment,
        transaction=transaction,
        renewal_info=renewal_info,
        state=state,
        raw=serialize_attrs(decoded),
    )
