# filename: createus_common/billing/tests/test_utils.py

import hashlib
import hmac

from django.test import SimpleTestCase

from createus_common.billing.utils.order_id import generate_order_id
from createus_common.billing.utils.signatures import verify_hmac_sha256


class GenerateOrderIdTests(SimpleTestCase):
    def test_default_prefix_is_ord(self):
        self.assertTrue(generate_order_id().startswith("ord_"))

    def test_custom_prefix_is_applied(self):
        self.assertTrue(generate_order_id(prefix="plaw").startswith("plaw_"))

    def test_order_id_is_url_safe_and_within_toss_length_limit(self):
        order_id = generate_order_id(prefix="plaw")
        self.assertLessEqual(len(order_id), 64)
        allowed = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        )
        self.assertTrue(set(order_id) <= allowed)

    def test_order_ids_are_unique(self):
        ids = {generate_order_id() for _ in range(200)}
        self.assertEqual(len(ids), 200)


class VerifyHmacSha256Tests(SimpleTestCase):
    def test_valid_signature_returns_true(self):
        secret = "webhook-secret"
        payload = b'{"eventType":"PAYMENT_STATUS_CHANGED"}'
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        self.assertTrue(verify_hmac_sha256(payload, signature, secret))

    def test_invalid_signature_returns_false(self):
        payload = b'{"eventType":"PAYMENT_STATUS_CHANGED"}'
        self.assertFalse(verify_hmac_sha256(payload, "deadbeef", "webhook-secret"))

    def test_signature_computed_with_different_secret_is_rejected(self):
        payload = b"payload"
        signature = hmac.new(b"secret-a", payload, hashlib.sha256).hexdigest()
        self.assertFalse(verify_hmac_sha256(payload, signature, "secret-b"))

    def test_signature_is_payload_specific(self):
        secret = "webhook-secret"
        signature = hmac.new(secret.encode(), b"payload-a", hashlib.sha256).hexdigest()
        self.assertFalse(verify_hmac_sha256(b"payload-b", signature, secret))
