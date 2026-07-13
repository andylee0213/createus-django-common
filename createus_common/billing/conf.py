# filename: createus_common/billing/conf.py

"""
Generic (provider-agnostic) settings resolution for ``createus_common.billing``.

This is what lets a concrete project "install createus-django-common and
include the billing urls" without subclassing any view: the generic views
in ``createus_common.billing.views`` resolve the concrete subscription model
through ``get_subscription_model()`` at request time, the same way Django's
own ``AUTH_USER_MODEL`` works.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_subscription_model():
    """
    Resolve the project's concrete subscription model.

    Configure in settings::

        CREATEUS_BILLING_SUBSCRIPTION_MODEL = "accounts.UserSubscription"

    The referenced model must subclass
    ``createus_common.billing.models.AbstractUserSubscription`` and define a
    FK/O2O field named ``user`` pointing at ``AUTH_USER_MODEL``.
    """
    model_path = getattr(settings, "CREATEUS_BILLING_SUBSCRIPTION_MODEL", None)
    if not model_path:
        raise ImproperlyConfigured(
            "CREATEUS_BILLING_SUBSCRIPTION_MODEL must be set to 'app_label.ModelName', "
            "pointing at a concrete subclass of AbstractUserSubscription with a "
            "`user` FK/O2O field."
        )
    try:
        return django_apps.get_model(model_path, require_ready=False)
    except (LookupError, ValueError) as exc:
        raise ImproperlyConfigured(
            f"CREATEUS_BILLING_SUBSCRIPTION_MODEL refers to model '{model_path}' "
            "which is not installed. Check INSTALLED_APPS and the setting value."
        ) from exc


def get_store_transaction_model():
    """
    Optional. Configure only if the project wants the shared transaction
    ledger persisted::

        CREATEUS_BILLING_STORE_TRANSACTION_MODEL = "accounts.StoreTransaction"

    The referenced model must subclass
    ``createus_common.billing.models.AbstractStoreTransaction``. Returns
    ``None`` if not configured — the entitlement engine treats that as
    "don't persist a ledger row", which is a valid (if less auditable)
    configuration.
    """
    model_path = getattr(settings, "CREATEUS_BILLING_STORE_TRANSACTION_MODEL", None)
    if not model_path:
        return None
    try:
        return django_apps.get_model(model_path, require_ready=False)
    except (LookupError, ValueError) as exc:
        raise ImproperlyConfigured(
            f"CREATEUS_BILLING_STORE_TRANSACTION_MODEL refers to model '{model_path}' "
            "which is not installed."
        ) from exc


def get_store_notification_model():
    """
    Configure to enable idempotent notification processing::

        CREATEUS_BILLING_STORE_NOTIFICATION_MODEL = "accounts.StoreNotification"

    The referenced model must subclass
    ``createus_common.billing.models.AbstractStoreNotification``. Strongly
    recommended in production — without it, duplicate webhook deliveries
    from Apple are reprocessed (and re-fire signals) on every retry.
    """
    model_path = getattr(settings, "CREATEUS_BILLING_STORE_NOTIFICATION_MODEL", None)
    if not model_path:
        return None
    try:
        return django_apps.get_model(model_path, require_ready=False)
    except (LookupError, ValueError) as exc:
        raise ImproperlyConfigured(
            f"CREATEUS_BILLING_STORE_NOTIFICATION_MODEL refers to model '{model_path}' "
            "which is not installed."
        ) from exc
