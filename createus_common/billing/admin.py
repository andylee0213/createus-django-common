# filename: createus_common/billing/admin.py

"""
Abstract models can't be registered with Django admin directly. These
mixins let each concrete project compose a normal ``ModelAdmin`` for its own
subscription/transaction/notification models while getting sensible
``list_display``/``list_filter``/``search_fields`` defaults for free.

Usage in a project's admin.py::

    from django.contrib import admin
    from createus_common.billing.admin import (
        StoreNotificationAdminMixin,
        StoreTransactionAdminMixin,
        UserSubscriptionAdminMixin,
    )
    from .models import StoreNotification, StoreTransaction, UserSubscription

    @admin.register(UserSubscription)
    class UserSubscriptionAdmin(UserSubscriptionAdminMixin, admin.ModelAdmin):
        pass

    @admin.register(StoreTransaction)
    class StoreTransactionAdmin(StoreTransactionAdminMixin, admin.ModelAdmin):
        pass

    @admin.register(StoreNotification)
    class StoreNotificationAdmin(StoreNotificationAdminMixin, admin.ModelAdmin):
        pass
"""


class UserSubscriptionAdminMixin:
    list_display = (
        "id",
        "user",
        "provider",
        "status",
        "product_id",
        "environment",
        "expires_at",
        "auto_renew_status",
        "is_in_billing_retry_period",
    )
    list_filter = ("provider", "status", "environment", "auto_renew_status")
    search_fields = ("external_subscription_id", "product_id")
    readonly_fields = ("created_at", "updated_at")


class StoreTransactionAdminMixin:
    list_display = (
        "id",
        "provider",
        "original_transaction_id",
        "transaction_id",
        "product_id",
        "transaction_type",
        "transaction_reason",
        "purchase_date",
        "expires_date",
        "revocation_date",
    )
    list_filter = ("provider", "environment", "transaction_type", "transaction_reason")
    search_fields = ("original_transaction_id", "transaction_id", "product_id")
    readonly_fields = ("created_at", "updated_at")


class StoreNotificationAdminMixin:
    list_display = (
        "id",
        "provider",
        "notification_type",
        "subtype",
        "original_transaction_id",
        "processing_status",
        "created_at",
        "processed_at",
    )
    list_filter = ("provider", "notification_type", "processing_status")
    search_fields = ("notification_uuid", "original_transaction_id")
    readonly_fields = ("created_at", "updated_at", "processed_at")
