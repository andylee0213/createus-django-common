# filename: createus_common/billing/utils/order_id.py

import uuid


def generate_order_id(prefix: str = "ord") -> str:
    """
    Return a URL-safe, non-sequential order identifier suitable for use as
    TossPayments ``orderId`` (max 64 chars, alphanumeric + hyphens/underscores).

    Format: ``{prefix}_{32-char uuid4 hex}``
    Example: ``ord_4b3f2e1a8c7d6e5f4a3b2c1d0e9f8a7b``

    uuid4 guarantees sufficient uniqueness without leaking sequence
    information.  The hex representation is URL-safe with no special chars.
    """
    uid = uuid.uuid4().hex
    return f"{prefix}_{uid}"
