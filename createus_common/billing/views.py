# filename: createus_common/billing/views.py

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from createus_common.billing.exceptions import (
    BillingException,
    StoreAPIException,
    TransactionVerificationException,
)
from createus_common.billing.serializers import (
    ActivateAppStoreSubscriptionSerializer,
    AppStoreServerNotificationSerializer,
    SubscriptionStateSerializer,
)
from createus_common.billing.services.apple import AppleSubscriptionSyncService


class AppStoreActivateSubscriptionView(APIView):
    """
    POST {"signed_transaction_info": "<JWS from StoreKit 2>"}

    Verifies the transaction, independently re-checks its live status with
    Apple's App Store Server API, and activates/refreshes the caller's
    subscription accordingly. The server never trusts a client-reported
    plan/boolean — see ``AppleSubscriptionSyncService.activate_for_user``.
    Used for both the initial-purchase flow and "Restore Purchases"
    (StoreKit hands the client the same kind of signed transaction either
    way, so no separate restore endpoint is needed).

    Override ``get_service`` if a project needs a differently-configured
    ``AppleSubscriptionSyncService`` (e.g. non-default provider settings);
    the default resolves everything from Django settings.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_service(self) -> AppleSubscriptionSyncService:
        return AppleSubscriptionSyncService()

    def post(self, request):
        serializer = ActivateAppStoreSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            subscription = self.get_service().activate_for_user(
                user=request.user,
                signed_transaction_info=serializer.validated_data["signed_transaction_info"],
            )
        except TransactionVerificationException as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except StoreAPIException as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except BillingException as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(SubscriptionStateSerializer(subscription).data)


class AppStoreServerNotificationsView(APIView):
    """
    Receiver for App Store Server Notifications V2. Register this exact URL
    as the "Production Server URL" / "Sandbox Server URL" in App Store
    Connect (App Information → App Store Server Notifications).

    No user auth: Apple's servers call this directly, authenticated purely
    by the JWS signature inside the body — there is no session/token to
    check, and requiring one would just mean Apple can't deliver. Returns a
    non-2xx on any verification/processing failure so Apple retries with
    its own exponential backoff (Apple keeps retrying for up to ~24 hours).
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_service(self) -> AppleSubscriptionSyncService:
        return AppleSubscriptionSyncService()

    def post(self, request):
        serializer = AppStoreServerNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            self.get_service().handle_notification(serializer.validated_data["signedPayload"])
        except TransactionVerificationException as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except BillingException as exc:
            # Any other billing-layer failure: surface 5xx so Apple retries
            # instead of treating a transient DB/processing error as delivered.
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(status=status.HTTP_200_OK)
