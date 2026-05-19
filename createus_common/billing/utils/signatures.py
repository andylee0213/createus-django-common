# filename: createus_common/billing/utils/signatures.py

import hashlib
import hmac


def verify_hmac_sha256(payload: bytes, signature: str, secret: str) -> bool:
    """
    Constant-time comparison of an HMAC-SHA256 digest against a provider-
    supplied signature hex string.

    Returns True only when the signature is valid.
    """
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
