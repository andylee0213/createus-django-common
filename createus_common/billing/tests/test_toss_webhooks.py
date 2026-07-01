# filename: createus_common/billing/tests/test_toss_webhooks.py

import json
from types import SimpleNamespace

from django.test import SimpleTestCase

from createus_common.billing.choices import PaymentStatus
from createus_common.billing.exceptions import WebhookVerificationException
from createus_common.billing.webhooks.toss import (
    PAYMENT_STATUS_CHANGED,
    TossWebhookHandler,
    normalize_toss_payment_status,
)


def _request(body):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return SimpleNamespace(body=raw)


class NormalizeTossPaymentStatusTests(SimpleTestCase):
    def test_known_statuses_map_to_shared_payment_status(self):
        cases = {
            "DONE": PaymentStatus.DONE,
            "CANCELED": PaymentStatus.CANCELLED,
            "PARTIAL_CANCELED": PaymentStatus.PARTIAL_CANCELLED,
            "ABORTED": PaymentStatus.ABORTED,
            "EXPIRED": PaymentStatus.EXPIRED,
            "FAILED": PaymentStatus.FAILED,
        }
        for toss_status, expected in cases.items():
            with self.subTest(toss_status=toss_status):
                self.assertEqual(normalize_toss_payment_status(toss_status), expected)

    def test_unknown_status_returns_none(self):
        self.assertIsNone(normalize_toss_payment_status("SOME_FUTURE_STATUS"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(normalize_toss_payment_status(""))


class TossWebhookHandlerVerifyTests(SimpleTestCase):
    def test_verify_skips_when_no_secret_configured(self):
        handler = TossWebhookHandler(webhook_secret=None)
        handler.verify(_request({"secret": "whatever"}))  # must not raise

    def test_verify_passes_with_matching_secret(self):
        handler = TossWebhookHandler(webhook_secret="correct")
        handler.verify(_request({"secret": "correct"}))  # must not raise

    def test_verify_raises_on_mismatched_secret(self):
        handler = TossWebhookHandler(webhook_secret="correct")
        with self.assertRaises(WebhookVerificationException):
            handler.verify(_request({"secret": "wrong"}))

    def test_verify_raises_on_missing_secret_field(self):
        handler = TossWebhookHandler(webhook_secret="correct")
        with self.assertRaises(WebhookVerificationException):
            handler.verify(_request({"eventType": PAYMENT_STATUS_CHANGED}))

    def test_verify_raises_on_invalid_json_body(self):
        handler = TossWebhookHandler(webhook_secret="correct")
        with self.assertRaises(WebhookVerificationException):
            handler.verify(_request(b"not json"))


class TossWebhookHandlerParseTests(SimpleTestCase):
    def test_parse_returns_event_type_and_payload(self):
        handler = TossWebhookHandler()
        event_type, payload = handler.parse(
            _request({"eventType": PAYMENT_STATUS_CHANGED, "data": {"status": "DONE"}})
        )
        self.assertEqual(event_type, PAYMENT_STATUS_CHANGED)
        self.assertEqual(payload["data"]["status"], "DONE")

    def test_parse_raises_when_event_type_missing(self):
        handler = TossWebhookHandler()
        with self.assertRaises(WebhookVerificationException):
            handler.parse(_request({"data": {}}))

    def test_parse_raises_on_invalid_json_body(self):
        handler = TossWebhookHandler()
        with self.assertRaises(WebhookVerificationException):
            handler.parse(_request(b"not json"))


class TossWebhookHandlerProcessTests(SimpleTestCase):
    def test_process_dispatches_to_registered_handler(self):
        handler = TossWebhookHandler()
        received = []
        handler.register_handler(PAYMENT_STATUS_CHANGED, received.append)
        handler.process(PAYMENT_STATUS_CHANGED, {"data": {}})
        self.assertEqual(len(received), 1)

    def test_process_dispatches_to_multiple_handlers_in_registration_order(self):
        handler = TossWebhookHandler()
        received = []
        handler.register_handler(PAYMENT_STATUS_CHANGED, lambda p: received.append("first"))
        handler.register_handler(PAYMENT_STATUS_CHANGED, lambda p: received.append("second"))
        handler.process(PAYMENT_STATUS_CHANGED, {})
        self.assertEqual(received, ["first", "second"])

    def test_process_is_noop_for_unregistered_event_type(self):
        handler = TossWebhookHandler()
        handler.process("SOME_OTHER_EVENT", {})  # must not raise
