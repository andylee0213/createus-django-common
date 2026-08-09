# filename: createus_common/billing/tests/test_apple_client.py

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from appstoreserverlibrary.api_client import APIException
from appstoreserverlibrary.models.JWSTransactionDecodedPayload import JWSTransactionDecodedPayload
from appstoreserverlibrary.models.Status import Status
from appstoreserverlibrary.signed_data_verifier import VerificationException, VerificationStatus

from createus_common.billing.exceptions import StoreAPIException, TransactionVerificationException
from createus_common.billing.providers.apple.client import AppleAppStoreProvider


def _make_provider(verifier=None, api_client=None) -> AppleAppStoreProvider:
    """
    Construct an AppleAppStoreProvider without running ``__init__`` (which
    would otherwise require real Django settings, a signing key, and root
    certificates). Only the two collaborators every method delegates to are
    faked; the conversion/error-wrapping logic under test is unmodified.
    """
    provider = object.__new__(AppleAppStoreProvider)
    provider._verifier = verifier or Mock()
    provider._api_client = api_client or Mock()
    return provider


class VerifyAndDecodeTransactionTests(SimpleTestCase):
    def test_wraps_verification_exception(self):
        verifier = Mock()
        verifier.verify_and_decode_signed_transaction.side_effect = VerificationException(
            VerificationStatus.INVALID_CHAIN
        )
        provider = _make_provider(verifier=verifier)
        with self.assertRaises(TransactionVerificationException):
            provider.verify_and_decode_transaction("bad-jws")

    def test_returns_normalized_transaction_on_success(self):
        decoded = JWSTransactionDecodedPayload(originalTransactionId="orig-1", transactionId="txn-1")
        verifier = Mock()
        verifier.verify_and_decode_signed_transaction.return_value = decoded
        provider = _make_provider(verifier=verifier)
        normalized = provider.verify_and_decode_transaction("good-jws")
        self.assertEqual(normalized.original_transaction_id, "orig-1")
        self.assertEqual(normalized.transaction_id, "txn-1")


class VerifyAndDecodeNotificationTests(SimpleTestCase):
    def test_wraps_verification_exception(self):
        verifier = Mock()
        verifier.verify_and_decode_notification.side_effect = VerificationException(
            VerificationStatus.INVALID_CERTIFICATE
        )
        provider = _make_provider(verifier=verifier)
        with self.assertRaises(TransactionVerificationException):
            provider.verify_and_decode_notification("bad-payload")


class GetSubscriptionStatusesTests(SimpleTestCase):
    def test_wraps_api_exception(self):
        api_client = Mock()
        api_client.get_all_subscription_statuses.side_effect = APIException(
            http_status_code=500, raw_api_error=5000000, error_message="boom"
        )
        provider = _make_provider(api_client=api_client)
        with self.assertRaises(StoreAPIException):
            provider.get_subscription_statuses("orig-1")

    def test_snapshot_with_no_signed_info_has_none_transaction_and_renewal(self):
        item = SimpleNamespace(status=Status.ACTIVE, signedTransactionInfo=None, signedRenewalInfo=None)
        group = SimpleNamespace(subscriptionGroupIdentifier="group1", lastTransactions=[item])
        response = SimpleNamespace(data=[group])

        api_client = Mock()
        api_client.get_all_subscription_statuses.return_value = response
        provider = _make_provider(api_client=api_client)

        snapshots = provider.get_subscription_statuses("orig-1")
        self.assertEqual(len(snapshots), 1)
        self.assertIsNone(snapshots[0].transaction)
        self.assertIsNone(snapshots[0].renewal_info)

    def test_decodes_signed_transaction_when_present(self):
        decoded = JWSTransactionDecodedPayload(originalTransactionId="orig-1", transactionId="txn-1")
        item = SimpleNamespace(
            status=Status.ACTIVE, signedTransactionInfo="jws-txn", signedRenewalInfo=None
        )
        group = SimpleNamespace(subscriptionGroupIdentifier="group1", lastTransactions=[item])
        response = SimpleNamespace(data=[group])

        api_client = Mock()
        api_client.get_all_subscription_statuses.return_value = response
        verifier = Mock()
        verifier.verify_and_decode_signed_transaction.return_value = decoded
        provider = _make_provider(verifier=verifier, api_client=api_client)

        snapshots = provider.get_subscription_statuses("orig-1")
        self.assertEqual(snapshots[0].transaction.original_transaction_id, "orig-1")

    def test_unrecognized_status_value_is_skipped(self):
        item = SimpleNamespace(status=Status.ACTIVE, signedTransactionInfo=None, signedRenewalInfo=None)
        group = SimpleNamespace(subscriptionGroupIdentifier="group1", lastTransactions=[item])
        response = SimpleNamespace(data=[group])

        api_client = Mock()
        api_client.get_all_subscription_statuses.return_value = response
        provider = _make_provider(api_client=api_client)

        with patch(
            "createus_common.billing.providers.apple.client.status_to_state", return_value=None
        ):
            snapshots = provider.get_subscription_statuses("orig-1")
        self.assertEqual(snapshots, [])
