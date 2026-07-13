# filename: createus_common/billing/providers/apple/conf.py

"""
Django settings resolution for the Apple App Store provider.

All values are read lazily (never at import time) so this module can be
imported before ``django.conf.settings`` is fully configured, and so a
missing/misconfigured value only breaks the request that actually needs it
instead of failing app startup.

Required settings (see docs/billing.md for how to obtain each one)::

    APPSTORE_BUNDLE_ID              = "com.cookthis.pro"
    APPSTORE_ISSUER_ID              = "99b16628-15e4-4668-972b-eeff55eeff55"
    APPSTORE_KEY_ID                 = "ABCDEFGHIJ"
    APPSTORE_PRIVATE_KEY            = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
    # or, equivalently:
    APPSTORE_PRIVATE_KEY_PATH       = "/secrets/SubscriptionKey_ABCDEFGHIJ.p8"
    APPSTORE_ROOT_CERTIFICATE_PATHS = ["/secrets/apple/AppleRootCA-G3.cer"]
    APPSTORE_ENVIRONMENT             = "production"  # or "sandbox"

Optional::

    APPSTORE_APP_APPLE_ID            = 123456789   # required once environment == "production"
    APPSTORE_ENABLE_ONLINE_CHECKS     = True         # default True
"""

from __future__ import annotations

from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from appstoreserverlibrary.models.Environment import Environment


def _setting(name: str, default=None):
    return getattr(settings, name, default)


def _require(name: str) -> str:
    value = _setting(name)
    if not value:
        raise ImproperlyConfigured(
            f"{name} must be set in Django settings to use the Apple App "
            "Store provider. See createus_common/billing docs/billing.md."
        )
    return value


def get_environment() -> Environment:
    raw = _setting("APPSTORE_ENVIRONMENT", "production")
    normalized = str(raw).strip().lower()
    if normalized == "sandbox":
        return Environment.SANDBOX
    if normalized == "production":
        return Environment.PRODUCTION
    raise ImproperlyConfigured(
        f"APPSTORE_ENVIRONMENT must be 'sandbox' or 'production', got {raw!r}."
    )


def get_bundle_id() -> str:
    return _require("APPSTORE_BUNDLE_ID")


def get_issuer_id() -> str:
    return _require("APPSTORE_ISSUER_ID")


def get_key_id() -> str:
    return _require("APPSTORE_KEY_ID")


def get_signing_key() -> bytes:
    """
    Returns the PEM-encoded App Store Connect API private key as bytes.

    Prefer ``APPSTORE_PRIVATE_KEY`` (the raw PEM text) in production so the
    key can be injected as a secret-manager value; ``APPSTORE_PRIVATE_KEY_PATH``
    is provided for local development convenience.
    """
    inline = _setting("APPSTORE_PRIVATE_KEY")
    if inline:
        return inline.encode("utf-8") if isinstance(inline, str) else inline

    path = _setting("APPSTORE_PRIVATE_KEY_PATH")
    if path:
        with open(path, "rb") as fh:
            return fh.read()

    raise ImproperlyConfigured(
        "Either APPSTORE_PRIVATE_KEY or APPSTORE_PRIVATE_KEY_PATH must be "
        "set in Django settings to use the Apple App Store provider."
    )


@lru_cache(maxsize=None)
def _read_certificate_file(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def get_root_certificates() -> list[bytes]:
    """
    Returns Apple's root CA certificates (DER-encoded .cer files) used to
    validate the x5c chain embedded in every JWS Apple signs.

    Download the current roots from
    https://www.apple.com/certificateauthority/ (Apple Root CA - G3 is the
    one used by App Store Server signing as of 2024) and reference the
    on-disk paths here. The shared library intentionally does not vendor
    these bytes itself — verification is only meaningful against files each
    deploying project fetched and pinned themselves.
    """
    paths = _setting("APPSTORE_ROOT_CERTIFICATE_PATHS")
    if not paths:
        raise ImproperlyConfigured(
            "APPSTORE_ROOT_CERTIFICATE_PATHS must be set to a list of file "
            "paths pointing at Apple's root CA certificates (.cer, DER-encoded)."
        )
    return [_read_certificate_file(path) for path in paths]


def get_app_apple_id() -> int | None:
    """
    Numeric App Store Connect app id. Apple only populates/validates this in
    the *production* environment, so it is optional for sandbox-only setups.
    """
    value = _setting("APPSTORE_APP_APPLE_ID")
    if value is not None:
        return int(value)
    if get_environment() == Environment.PRODUCTION:
        raise ImproperlyConfigured(
            "APPSTORE_APP_APPLE_ID must be set once APPSTORE_ENVIRONMENT is "
            "'production' (Apple validates it against production notifications)."
        )
    return None


def get_enable_online_checks() -> bool:
    return bool(_setting("APPSTORE_ENABLE_ONLINE_CHECKS", True))
