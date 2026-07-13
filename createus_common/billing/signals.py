# filename: createus_common/billing/signals.py

"""
Subscription lifecycle signals.

``createus_common.billing`` deliberately does not know about any concrete
project's ``Plan`` model, feature flags, or usage limits — those are
project-specific. Instead, the entitlement engine fires these signals after
every state transition it computes, and each project connects its own
receivers (typically in its ``apps.py`` ``ready()``) to update whatever
bespoke fields it keeps (e.g. a ``plan`` enum, a cached ``is_pro`` flag,
sending an analytics event, revoking a cached feature-flag).

All signals are sent with these keyword arguments:

    sender             the AbstractEntitlementService subclass that fired it
    subscription       the concrete AbstractUserSubscription instance
    transaction         a createus_common.billing.providers.base.NormalizedTransaction,
                        or None for a plain expire()/cancel() call with no
                        backing store transaction
    previous_status     createus_common.billing.choices.SubscriptionStatus value
                        before this transition (or None if newly created)
    new_status          createus_common.billing.choices.SubscriptionStatus value
                        after this transition
"""

import django.dispatch

subscription_activated = django.dispatch.Signal()
subscription_renewed = django.dispatch.Signal()
subscription_entered_grace_period = django.dispatch.Signal()
subscription_entered_billing_retry = django.dispatch.Signal()
subscription_cancelled = django.dispatch.Signal()
subscription_expired = django.dispatch.Signal()
subscription_revoked = django.dispatch.Signal()
