# filename: createus_common/billing/providers/apple/client.py

from __future__ import annotations

from appstoreserverlibrary.api_client import AppStoreServerAPIClient, APIException
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException

from createus_common.billing.choices import PaymentProvider
from createus_common.billing.exceptions import StoreAPIException, TransactionVerificationException
from createus_common.billing.providers.apple import conf as apple_conf
from createus_common.billing.providers.apple.mapping import (
    decode_notification_to_normalized,
    decode_renewal_info_to_normalized,
    decode_transaction_to_normalized,
    status_to_state,
)
from createus_common.billing.providers.base import (
    AbstractStoreProvider,
    NormalizedNotification,
    NormalizedRenewalInfo,
    NormalizedTransaction,
    SubscriptionStatusSnapshot,
)


class AppleAppStoreProvider(AbstractStoreProvider):
    """
    App Store Server API + Notifications V2 integration, backed by Apple's
    official ``app-store-server-library``.

    Every method either returns cryptographically-verified, normalized data
    or raises ``TransactionVerificationException`` /
    ``createus_common.billing.exceptions.StoreAPIException`` — there is no
    path that returns client-supplied data unchecked.

    Configuration is resolved from Django settings via
    ``createus_common.billing.providers.apple.conf`` at construction time,
    so a misconfiguration surfaces immediately when the provider is
    instantiated rather than deep inside a request.
    """

    provider_id = PaymentProvider.APP_STORE

    def __init__(self, *, environment: Environment | None = None) -> None:
        self._environment = environment or apple_conf.get_environment()
        self._api_client = AppStoreServerAPIClient(
            signing_key=apple_conf.get_signing_key(),
            key_id=apple_conf.get_key_id(),
            issuer_id=apple_conf.get_issuer_id(),
            bundle_id=apple_conf.get_bundle_id(),
            environment=self._environment,
        )
        self._verifier = SignedDataVerifier(
            root_certificates=apple_conf.get_root_certificates(),
            enable_online_checks=apple_conf.get_enable_online_checks(),
            environment=self._environment,
            bundle_id=apple_conf.get_bundle_id(),
            app_apple_id=apple_conf.get_app_apple_id(),
        )

    # ── AbstractStoreProvider ────────────────────────────────────────────────

    def verify_and_decode_transaction(self, signed_transaction: str) -> NormalizedTransaction:
        try:
            decoded = self._verifier.verify_and_decode_signed_transaction(signed_transaction)
        except VerificationException as exc:
            raise TransactionVerificationException(
                f"App Store transaction verification failed: {exc.status.name}"
            ) from exc
        return decode_transaction_to_normalized(decoded)

    def verify_and_decode_renewal_info(self, signed_renewal_info: str) -> NormalizedRenewalInfo:
        try:
            decoded = self._verifier.verify_and_decode_renewal_info(signed_renewal_info)
        except VerificationException as exc:
            raise TransactionVerificationException(
                f"App Store renewal info verification failed: {exc.status.name}"
            ) from exc
        return decode_renewal_info_to_normalized(decoded)

    def verify_and_decode_notification(self, signed_payload: str) -> NormalizedNotification:
        try:
            decoded = self._verifier.verify_and_decode_notification(signed_payload)
        except VerificationException as exc:
            raise TransactionVerificationException(
                f"App Store notification verification failed: {exc.status.name}"
            ) from exc
        return decode_notification_to_normalized(decoded, self)

    def get_subscription_statuses(
        self, original_transaction_id: str
    ) -> list[SubscriptionStatusSnapshot]:
        """
        The authoritative call: whatever a client claims about its purchase,
        this is what Apple's own servers say is currently true for every
        transaction in that subscription group. Each item's
        ``signedTransactionInfo``/``signedRenewalInfo`` is independently
        re-verified (not merely trusted because it came over an
        authenticated API connection) so the same signature-checking code
        path is exercised for API responses and client-submitted JWS alike.
        """
        try:
            response = self._api_client.get_all_subscription_statuses(original_transaction_id)
        except APIException as exc:
            raise StoreAPIException(
                message=exc.error_message or "App Store Server API request failed",
                code=str(exc.raw_api_error) if exc.raw_api_error is not None else "",
                raw={"http_status_code": exc.http_status_code},
            ) from exc

        snapshots: list[SubscriptionStatusSnapshot] = []
        for group in response.data or []:
            for item in group.lastTransactions or []:
                transaction = (
                    self.verify_and_decode_transaction(item.signedTransactionInfo)
                    if item.signedTransactionInfo
                    else None
                )
                renewal_info = (
                    self.verify_and_decode_renewal_info(item.signedRenewalInfo)
                    if item.signedRenewalInfo
                    else None
                )
                state = status_to_state(item.status)
                if state is None:
                    # Unknown/future status value from Apple — skip rather
                    # than guess at entitlement semantics we don't understand.
                    continue
                snapshots.append(
                    SubscriptionStatusSnapshot(
                        state=state,
                        transaction=transaction,
                        renewal_info=renewal_info,
                    )
                )
        return snapshots

    def request_test_notification(self) -> str:
        """
        Ask Apple to send a TEST notification to the configured webhook URL.
        Returns the ``testNotificationToken`` used to look up delivery
        status via the App Store Server API — useful for verifying webhook
        wiring in CI/staging without a real purchase.
        """
        try:
            response = self._api_client.request_test_notification()
        except APIException as exc:
            raise StoreAPIException(
                message=exc.error_message or "Failed to request test notification",
                code=str(exc.raw_api_error) if exc.raw_api_error is not None else "",
                raw={"http_status_code": exc.http_status_code},
            ) from exc
        return response.testNotificationToken
