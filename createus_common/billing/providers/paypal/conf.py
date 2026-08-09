# filename: createus_common/billing/providers/paypal/conf.py

"""
Django settings resolution for the PayPal provider.

All values are read lazily (never at import time, never cached module-level)
so a misconfiguration surfaces only when the request that actually needs it
runs, and so a value can be rotated by restarting the process without a code
change.

Required settings::

    PAYPAL_ENABLED        = True
    PAYPAL_MODE            = "sandbox"  # or "live"
    PAYPAL_CLIENT_ID       = "AZ..."
    PAYPAL_CLIENT_SECRET   = "EL..."    # never expose to templates/JS
    PAYPAL_WEBHOOK_ID      = "WH-..."   # from the configured webhook's detail page

Optional feature flags, defaulting to ``PAYPAL_ENABLED``'s value when unset::

    PAYPAL_ONE_TIME_ENABLED
    PAYPAL_SUBSCRIPTIONS_ENABLED

There is deliberately no fallback between sandbox and live, and no fallback
between different apps' credentials (e.g. PocketLaw vs. PocketTax) — each
Django project resolves its own settings module, so cross-app fallback would
require code in this shared library to know about apps it must never know
about. If a value is missing, fail loudly.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

SANDBOX = "sandbox"
LIVE = "live"

BASE_URLS = {
    SANDBOX: "https://api-m.sandbox.paypal.com",
    LIVE: "https://api-m.paypal.com",
}


def _setting(name: str, default=None):
    return getattr(settings, name, default)


def is_enabled() -> bool:
    return bool(_setting("PAYPAL_ENABLED", False))


def is_one_time_enabled() -> bool:
    value = _setting("PAYPAL_ONE_TIME_ENABLED", None)
    if value is None:
        return is_enabled()
    return bool(value)


def is_subscriptions_enabled() -> bool:
    value = _setting("PAYPAL_SUBSCRIPTIONS_ENABLED", None)
    if value is None:
        return is_enabled()
    return bool(value)


def get_mode() -> str:
    raw = _setting("PAYPAL_MODE", SANDBOX)
    normalized = str(raw).strip().lower()
    if normalized not in (SANDBOX, LIVE):
        raise ImproperlyConfigured(
            f"PAYPAL_MODE must be 'sandbox' or 'live', got {raw!r}."
        )
    return normalized


def get_base_url(mode: str | None = None) -> str:
    return BASE_URLS[mode or get_mode()]


def get_client_id() -> str:
    value = _setting("PAYPAL_CLIENT_ID")
    if not value:
        raise ImproperlyConfigured(
            "PAYPAL_CLIENT_ID must be set in Django settings to use the "
            "PayPal provider."
        )
    return value


def get_client_secret() -> str:
    value = _setting("PAYPAL_CLIENT_SECRET")
    if not value:
        raise ImproperlyConfigured(
            "PAYPAL_CLIENT_SECRET must be set in Django settings to use the "
            "PayPal provider."
        )
    return value


def get_webhook_id() -> str:
    value = _setting("PAYPAL_WEBHOOK_ID")
    if not value:
        raise ImproperlyConfigured(
            "PAYPAL_WEBHOOK_ID must be set in Django settings to verify "
            "PayPal webhook deliveries."
        )
    return value


def check_configuration() -> None:
    """
    Raise :exc:`ImproperlyConfigured` if PayPal is enabled but any required
    setting is missing. Intended to be called from a Django system check
    (``@register()`` in the concrete project's ``apps.py``) so a broken
    configuration fails deployment instead of failing the first checkout.
    """
    if not is_enabled():
        return
    get_mode()
    get_client_id()
    get_client_secret()
    get_webhook_id()
