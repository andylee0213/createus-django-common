# filename: createus_common/billing/tests/test_apple_mapping.py

from django.test import SimpleTestCase

from appstoreserverlibrary.models.AutoRenewStatus import AutoRenewStatus
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.models.ExpirationIntent import ExpirationIntent
from appstoreserverlibrary.models.InAppOwnershipType import InAppOwnershipType
from appstoreserverlibrary.models.JWSRenewalInfoDecodedPayload import JWSRenewalInfoDecodedPayload
from appstoreserverlibrary.models.JWSTransactionDecodedPayload import JWSTransactionDecodedPayload
from appstoreserverlibrary.models.OfferType import OfferType
from appstoreserverlibrary.models.RevocationReason import RevocationReason
from appstoreserverlibrary.models.Status import Status
from appstoreserverlibrary.models.TransactionReason import TransactionReason
from appstoreserverlibrary.models.Type import Type

from createus_common.billing.choices import PaymentProvider
from createus_common.billing.providers.apple.mapping import (
    decode_renewal_info_to_normalized,
    decode_transaction_to_normalized,
    status_to_state,
)
from createus_common.billing.providers.base import StoreSubscriptionState


def _transaction(**overrides) -> JWSTransactionDecodedPayload:
    defaults = dict(
        originalTransactionId="1000000000000001",
        transactionId="1000000000000002",
        productId="com.cookthis.pro.monthly",
        subscriptionGroupIdentifier="group1",
        purchaseDate=1_700_000_000_000,
        originalPurchaseDate=1_699_000_000_000,
        expiresDate=1_702_592_000_000,
        quantity=1,
        type=Type.AUTO_RENEWABLE_SUBSCRIPTION,
        inAppOwnershipType=InAppOwnershipType.PURCHASED,
        transactionReason=TransactionReason.PURCHASE,
        environment=Environment.SANDBOX,
        storefront="USA",
        storefrontId="143441",
        price=2990,
        currency="USD",
        isUpgraded=False,
    )
    defaults.update(overrides)
    return JWSTransactionDecodedPayload(**defaults)


class DecodeTransactionToNormalizedTests(SimpleTestCase):
    def test_maps_core_identity_fields(self):
        normalized = decode_transaction_to_normalized(_transaction())
        self.assertEqual(normalized.provider, PaymentProvider.APP_STORE)
        self.assertEqual(normalized.original_transaction_id, "1000000000000001")
        self.assertEqual(normalized.transaction_id, "1000000000000002")
        self.assertEqual(normalized.product_id, "com.cookthis.pro.monthly")
        self.assertEqual(normalized.environment, "sandbox")

    def test_maps_dates_from_epoch_milliseconds(self):
        normalized = decode_transaction_to_normalized(_transaction())
        self.assertEqual(normalized.expires_date.year, 2023)
        self.assertIsNotNone(normalized.purchase_date)
        self.assertIsNotNone(normalized.original_purchase_date)

    def test_maps_enum_fields_to_their_raw_values(self):
        normalized = decode_transaction_to_normalized(_transaction())
        self.assertEqual(normalized.transaction_type, "Auto-Renewable Subscription")
        self.assertEqual(normalized.in_app_ownership_type, "PURCHASED")
        self.assertEqual(normalized.transaction_reason, "PURCHASE")

    def test_maps_offer_type_to_int(self):
        normalized = decode_transaction_to_normalized(
            _transaction(offerType=OfferType.INTRODUCTORY_OFFER, offerIdentifier="intro")
        )
        self.assertEqual(normalized.offer_type, 1)
        self.assertEqual(normalized.offer_identifier, "intro")

    def test_offer_type_none_when_absent(self):
        normalized = decode_transaction_to_normalized(_transaction())
        self.assertIsNone(normalized.offer_type)

    def test_maps_revocation_fields(self):
        normalized = decode_transaction_to_normalized(
            _transaction(
                revocationDate=1_702_600_000_000,
                revocationReason=RevocationReason.REFUNDED_DUE_TO_ISSUE,
            )
        )
        self.assertIsNotNone(normalized.revocation_date)
        self.assertEqual(normalized.revocation_reason, 1)

    def test_no_revocation_fields_when_not_revoked(self):
        normalized = decode_transaction_to_normalized(_transaction())
        self.assertIsNone(normalized.revocation_date)
        self.assertIsNone(normalized.revocation_reason)

    def test_raw_is_json_safe_dict_with_no_enum_instances(self):
        normalized = decode_transaction_to_normalized(_transaction())
        self.assertIsInstance(normalized.raw, dict)
        self.assertEqual(normalized.raw["originalTransactionId"], "1000000000000001")
        # Every value in the flattened raw dict must already be a JSON-safe
        # primitive (str/int/bool/None/list/dict) — not an Enum member —
        # otherwise json.dumps() on this dict (e.g. before writing to a
        # JSONField) would raise.
        import json

        json.dumps(normalized.raw)


def _renewal_info(**overrides) -> JWSRenewalInfoDecodedPayload:
    defaults = dict(
        originalTransactionId="1000000000000001",
        autoRenewProductId="com.cookthis.pro.monthly",
        productId="com.cookthis.pro.monthly",
        autoRenewStatus=AutoRenewStatus.ON,
        isInBillingRetryPeriod=False,
        environment=Environment.SANDBOX,
        currency="USD",
        renewalPrice=2990,
    )
    defaults.update(overrides)
    return JWSRenewalInfoDecodedPayload(**defaults)


class DecodeRenewalInfoToNormalizedTests(SimpleTestCase):
    def test_maps_auto_renew_status_to_bool(self):
        normalized = decode_renewal_info_to_normalized(_renewal_info(autoRenewStatus=AutoRenewStatus.ON))
        self.assertIs(normalized.auto_renew_status, True)

    def test_maps_auto_renew_status_off_to_false(self):
        normalized = decode_renewal_info_to_normalized(_renewal_info(autoRenewStatus=AutoRenewStatus.OFF))
        self.assertIs(normalized.auto_renew_status, False)

    def test_maps_expiration_intent_to_int(self):
        normalized = decode_renewal_info_to_normalized(
            _renewal_info(expirationIntent=ExpirationIntent.BILLING_ERROR)
        )
        self.assertEqual(normalized.expiration_intent, 2)

    def test_maps_grace_period_expires_date(self):
        normalized = decode_renewal_info_to_normalized(
            _renewal_info(gracePeriodExpiresDate=1_702_700_000_000)
        )
        self.assertIsNotNone(normalized.grace_period_expires_date)

    def test_is_in_billing_retry_period_passthrough(self):
        normalized = decode_renewal_info_to_normalized(_renewal_info(isInBillingRetryPeriod=True))
        self.assertTrue(normalized.is_in_billing_retry_period)


class StatusToStateTests(SimpleTestCase):
    def test_active_maps_to_active(self):
        self.assertEqual(status_to_state(Status.ACTIVE), StoreSubscriptionState.ACTIVE)

    def test_billing_retry_maps_to_billing_retry(self):
        self.assertEqual(status_to_state(Status.BILLING_RETRY), StoreSubscriptionState.BILLING_RETRY)

    def test_billing_grace_period_maps_to_grace_period(self):
        self.assertEqual(
            status_to_state(Status.BILLING_GRACE_PERIOD), StoreSubscriptionState.GRACE_PERIOD
        )

    def test_expired_maps_to_expired(self):
        self.assertEqual(status_to_state(Status.EXPIRED), StoreSubscriptionState.EXPIRED)

    def test_revoked_maps_to_revoked(self):
        self.assertEqual(status_to_state(Status.REVOKED), StoreSubscriptionState.REVOKED)

    def test_none_maps_to_none(self):
        self.assertIsNone(status_to_state(None))
