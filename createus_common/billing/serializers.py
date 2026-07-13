# filename: createus_common/billing/serializers.py

from rest_framework import serializers


class ActivateAppStoreSubscriptionSerializer(serializers.Serializer):
    """
    The only thing a client ever submits to activate or refresh a
    subscription: the signed transaction JWS from StoreKit 2's
    ``Transaction.jwsRepresentation`` (the same value is used for the
    initial-purchase flow and for "Restore Purchases").

    Deliberately does NOT accept a plan name, a boolean, or a bare
    transaction id — accepting any of those would mean trusting client
    intent instead of independently verifying and re-deriving it from
    Apple's servers.
    """

    signed_transaction_info = serializers.CharField(trim_whitespace=False)


class AppStoreServerNotificationSerializer(serializers.Serializer):
    """Shape of the body Apple POSTs to the notifications webhook."""

    signedPayload = serializers.CharField(trim_whitespace=False)


class SubscriptionStateSerializer(serializers.Serializer):
    """
    Plain (non-Model) serializer — deliberately avoids DRF's
    ``ModelSerializer`` so it never needs to resolve the concrete,
    project-specific subscription model class at import time; it just
    reads attributes off whatever instance
    ``createus_common.billing.conf.get_subscription_model()`` returned.
    """

    provider = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    external_subscription_id = serializers.CharField()
    product_id = serializers.CharField()
    environment = serializers.CharField()
    started_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)
    cancelled_at = serializers.DateTimeField(allow_null=True)
    auto_renew_status = serializers.BooleanField(allow_null=True)
    is_in_billing_retry_period = serializers.BooleanField(allow_null=True)
    grace_period_expires_at = serializers.DateTimeField(allow_null=True)
    has_entitlement = serializers.SerializerMethodField()

    def get_provider(self, obj):
        return obj.get_provider_display() if obj.provider is not None else None

    def get_status(self, obj):
        return obj.get_status_display()

    def get_has_entitlement(self, obj):
        return obj.has_entitlement
