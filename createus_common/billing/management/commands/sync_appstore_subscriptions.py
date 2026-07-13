# filename: createus_common/billing/management/commands/sync_appstore_subscriptions.py

"""
Reconciliation job: re-fetches the authoritative App Store status for every
locally-known Apple subscription in a syncable state and re-applies it.

Corrects drift from a missed or delayed Notifications V2 delivery (network
blip, an instance down during delivery, etc.) without waiting for the user
to reopen the app. Notifications are the primary sync path — this is a
safety net, not the main entitlement pipeline — so running it daily (or
hourly, for higher-stakes apps) from whatever scheduler a project already
uses (cron, Celery beat, Cloud Scheduler, ...) is enough::

    python manage.py sync_appstore_subscriptions
    python manage.py sync_appstore_subscriptions --batch-size 500
"""

from django.core.management.base import BaseCommand

from createus_common.billing.choices import PaymentProvider, SubscriptionStatus
from createus_common.billing.conf import get_subscription_model
from createus_common.billing.exceptions import BillingException
from createus_common.billing.services.apple import AppleSubscriptionSyncService

_SYNCABLE_STATUSES = (
    SubscriptionStatus.TRIALING,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.GRACE_PERIOD,
    SubscriptionStatus.PAST_DUE,
)


class Command(BaseCommand):
    help = (
        "Reconcile locally-stored Apple App Store subscriptions against the "
        "App Store Server API, correcting drift from missed webhook deliveries."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Maximum number of subscriptions to sync in one run (default: 200).",
        )

    def handle(self, *args, **options):
        model = get_subscription_model()
        queryset = (
            model.objects.filter(
                provider=PaymentProvider.APP_STORE,
                status__in=_SYNCABLE_STATUSES,
            )
            .exclude(external_subscription_id="")
            .order_by("expires_at")[: options["batch_size"]]
        )

        service = AppleSubscriptionSyncService()
        synced = 0
        failed = 0
        for subscription in queryset:
            try:
                service.sync_subscription(subscription.external_subscription_id)
                synced += 1
            except BillingException as exc:
                failed += 1
                self.stderr.write(
                    self.style.WARNING(
                        f"Failed to sync subscription {subscription.pk} "
                        f"({subscription.external_subscription_id}): {exc}"
                    )
                )

        self.stdout.write(self.style.SUCCESS(f"Synced {synced} subscription(s), {failed} failure(s)."))
