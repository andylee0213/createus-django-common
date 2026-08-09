# billing

## Overview

`createus_common.billing` provides reusable building blocks for payment
processing and subscription management.  It is intentionally provider-agnostic
at the service layer; provider-specific HTTP calls live in
`createus_common.billing.providers`.

Project apps own:
- Concrete models (user FK, subscription rules, plan definitions)
- Subscription renewal scheduling (Celery beat, Cloud Scheduler, etc.)
- Frontend pages and redirect handlers
- Business rules (grace periods, dunning, feature gating)

---

## Toss Payments — Billing Keys (Automatic Recurring Payments)

### How it works

Toss Payments recurring billing uses a **billingKey** — a server-side token
that represents a user's registered card.  Once issued, the billingKey can be
charged server-to-server without further user interaction.

The registration flow uses the Toss JavaScript SDK on the frontend; the
backend never touches raw card numbers.

```
Frontend                         Backend                        Toss API
--------                         -------                        --------
requestBillingAuth(customerKey)
  → user enters card in Toss UI
  → Toss redirects to successUrl
    with authKey + customerKey
                                 BillingSuccessView receives
                                 authKey + customerKey
                                   ↓
                                 TossPaymentsClient
                                   .issue_billing_key(
                                       auth_key, customer_key)
                                                              POST /v1/billing/
                                                                authorizations/issue
                                                              ← billingKey
                                 Store BillingKeyRecord
                                 Activate subscription
```

### `TossPaymentsClient` methods

| Method | Endpoint | Timeout | Purpose |
|---|---|---|---|
| `issue_billing_key(auth_key, customer_key)` | `POST /v1/billing/authorizations/issue` | 10 s | Exchange SDK authKey for billingKey |
| `charge_billing_key(billing_key, ...)` | `POST /v1/billing/{billingKey}` | **60 s** | Charge stored billingKey |
| `revoke_billing_key(billing_key)` | `DELETE /v1/billing/{billingKey}` | 10 s | Remove card / cancel billing |

> **Why 60 s for `charge_billing_key`?**  Toss states that billing approval
> from some card issuers can take up to 60 seconds.  Network timeouts shorter
> than this will produce false-failure `ProviderConnectionException` errors on
> legitimate approvals.

### `charge_billing_key` optional parameters

| Parameter | Default | Notes |
|---|---|---|
| `customer_email` | `None` | Omitted from request if not provided |
| `customer_name` | `None` | Omitted from request if not provided |
| `customer_ip` | `None` | Omitted from request if not provided |
| `tax_free_amount` | `0` | Always included |
| `tax_exemption_amount` | `0` | Always included |

### Exceptions

| Exception | When raised |
|---|---|
| `BillingKeyIssueException` | `issue_billing_key` — Toss returns non-2xx |
| `BillingKeyChargeException` | `charge_billing_key` — Toss returns non-2xx |
| `BillingKeyRevokeException` | `revoke_billing_key` — Toss returns non-2xx |
| `ProviderConnectionException` | Network-level failure on any call |

All three billing exceptions extend `ProviderException` and carry `.code` and
`.raw` attributes from the Toss error response.

### Security rules

- **Do not log the full `billingKey`.**  It is a credential equivalent to a
  stored card token.  `TossPaymentsClient` never writes it to exception
  messages.
- **Encrypt `billing_key` at rest** in the concrete `BillingKeyRecord` model.
  Use Django's `EncryptedField` or equivalent.
- The `raw_response` field on `AbstractBillingKeyRecord` may contain the full
  Toss response for audit purposes.  Redact `billingKey` before shipping logs
  to external systems.
- **Do not implement `/v1/billing/authorizations/card`.**  Direct card-number
  collection is prohibited in Createus apps.  Use the SDK `authKey` flow only.

### `AbstractBillingKeyRecord`

Defined in `createus_common.billing.models.billing_keys`.  Project apps
subclass this and add a `user` foreign key.

```python
from createus_common.billing.models import AbstractBillingKeyRecord

class BillingKeyRecord(AbstractBillingKeyRecord):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="billing_key_record",
    )

    class Meta:
        db_table = "billing_key_records"
```

The shared library does not add a `user` FK because the auth model is
project-specific.

### What the shared library does NOT own

- `requestBillingAuth()` — frontend SDK call; project app's template
- `/billing/subscribe/` — project app view
- `/billing/billing-success/` — project app view
- `/billing/billing-fail/` — project app view
- Subscription renewal scheduling — project app Celery tasks
- Grace periods, dunning, feature gating — project app business logic

---

## PayPal (Orders v2, Subscriptions v1, Webhooks)

### How it works

`createus_common.billing.providers.paypal.PayPalClient` wraps three PayPal
REST surfaces behind one `httpx`-based client:

- **Orders v2** — one-time CAPTURE-intent payments (`create_order`,
  `get_order`, `capture_order`, `refund_capture`).
- **Subscriptions v1** — recurring billing (`create_catalog_product`,
  `create_plan`, `get_plan`, `create_subscription`, `get_subscription`,
  `cancel_subscription`, `suspend_subscription`, `activate_subscription`,
  `revise_subscription`).
- **Webhooks** — `verify_webhook_signature`, wrapping
  `POST /v1/notifications/verify-webhook-signature`.

OAuth2 client-credentials access tokens are fetched from
`POST /v1/oauth2/token` and cached **per-process**, keyed by
`(mode, client_id)`, with a 60-second expiry safety margin — callers never
need to manage the token themselves.

```python
from createus_common.billing.providers.paypal import PayPalClient

client = PayPalClient()  # reads PAYPAL_MODE/CLIENT_ID/CLIENT_SECRET from settings
order = client.create_order(
    amount="49.00", currency="USD",
    reference_id=purchase.order_id, request_id=purchase.order_id,
)
```

### Settings

```python
PAYPAL_ENABLED = True
PAYPAL_MODE = "sandbox"            # or "live" — no fallback between them
PAYPAL_CLIENT_ID = "..."           # not secret; safe to render to the JS SDK
PAYPAL_CLIENT_SECRET = "..."       # never expose to templates/JS/logs
PAYPAL_WEBHOOK_ID = "..."          # from the webhook's detail page in the Dashboard
```

Read via `createus_common.billing.providers.paypal.conf` — `is_enabled()`,
`get_mode()`, `get_base_url()`, `get_client_id()`, `get_client_secret()`,
`get_webhook_id()`, `check_configuration()`. Call `check_configuration()` from
a Django system check in the concrete project (see PocketLaw's
`billing/checks.py`) so an enabled-but-incomplete configuration fails
`manage.py check` / deployment rather than the first checkout.

### Idempotency

Every mutating POST (`create_order`, `capture_order`, `refund_capture`,
`create_catalog_product`, `create_plan`, `create_subscription`,
`cancel_subscription`, `suspend_subscription`, `activate_subscription`,
`revise_subscription`) accepts a `request_id` keyword, sent as the
`PayPal-Request-Id` header — PayPal's own idempotency key. Callers should pass
a **deterministic** value derived from the local record (e.g. the local
order id, or `f"paypal-plan-{plan.id}-{mode}"`) so a retried call cannot
create a duplicate order/plan/subscription at PayPal.

### Exceptions

| Exception | When raised |
|---|---|
| `PayPalAuthException` | OAuth2 token request returns non-2xx or a malformed body |
| `PayPalOrderException` | Any Orders v2 call returns non-2xx |
| `PayPalSubscriptionException` | Any Subscriptions v1 call returns non-2xx |
| `WebhookVerificationException` | Missing transmission headers, a non-2xx from the verify endpoint, or `verification_status != "SUCCESS"` |
| `ProviderConnectionException` | Network-level failure (including timeout) on any call |

All four typed exceptions extend `ProviderException` and carry `.code`/`.raw`;
`.raw` is defensively redacted of any key containing `secret`, `token`, or
`authorization` before being attached. No exception message ever contains the
access token or client secret.

### Webhook verification

```python
client.verify_webhook_signature(
    headers=request.headers,   # case-insensitive; PAYPAL-* headers required
    raw_event=payload,          # the exact parsed JSON body PayPal sent
)
```

Raises `WebhookVerificationException` for anything other than
`verification_status == "SUCCESS"` — always call this before trusting an
event id for deduplication or acting on its contents. See PocketLaw's
`billing/views_paypal_webhooks.py` for the full verify → dedupe → re-fetch
→ apply pattern.

### What the shared library does NOT own

- Which local model represents a PayPal order/capture/subscription id —
  project apps add provider-neutral fields (`provider_order_id`,
  `provider_capture_id`, `external_subscription_id`) to their own concrete
  models.
- The PayPal JS SDK integration (`paypal.Buttons(...)`) — project app
  templates/static JS.
- Catalog product / plan **sync** — project apps own a
  `manage.py sync_paypal_subscription_plans`-style command; the shared
  client only exposes the underlying `create_catalog_product`/`create_plan`
  calls.
- Webhook event storage/dedup model — project apps define their own (or
  reuse `AbstractStoreNotification` if its shape fits).
- Entitlement/access-grant logic — project app business rules.

---

## Apple App Store (In-App Purchase Subscriptions)

### Why this exists

The naive way to "activate" a subscription after a StoreKit purchase is for
the client to call a backend endpoint with something like
`{"original_transaction_id": "..."}` and have the server flip a `plan` flag
to `pro`. **That is a client-trust vulnerability**: any authenticated user
can call that endpoint with a fabricated or someone-else's transaction id
and grant themselves paid access, because the server never independently
confirms the purchase happened.

`createus_common.billing.providers.apple` + `services.apple` +
`services.entitlement` replace that with a flow where **the server is the
only source of truth**:

1. The client submits the **signed transaction JWS** from StoreKit 2
   (`Transaction.jwsRepresentation`), never a bare id or boolean.
2. The server cryptographically verifies the JWS against Apple's root CA
   (rejects anything not actually signed by Apple, for the wrong bundle id,
   or from the wrong environment).
3. The server then calls the **App Store Server API**
   (`get_all_subscription_statuses`) directly against Apple's servers for
   the *current* status of that subscription — a client cannot advance its
   own entitlement by replaying an old-but-validly-signed JWS from a
   since-cancelled or refunded purchase, because this step always re-derives
   live state.
4. **App Store Server Notifications V2** keep every subscription's state
   correct in near-real-time afterwards (renewals, cancellations, refunds,
   revocations, billing retry, grace period) without the client ever being
   involved again.
5. A daily reconciliation job (`sync_appstore_subscriptions`) is a safety
   net against a missed notification delivery.

### Install

```
pip install createus-django-common[apple]
```

Installs Apple's official
[`app-store-server-library`](https://github.com/apple/app-store-server-library-python)
(JWT signing for API auth, JWS verification, App Store Server API client).

### Settings

```python
INSTALLED_APPS = [
    ...,
    "createus_common.billing.apps.CreateusBillingConfig",
    "accounts",  # wherever your concrete models live
]

# Generic (provider-agnostic) — required
CREATEUS_BILLING_SUBSCRIPTION_MODEL = "accounts.UserSubscription"

# Recommended — without these, the transaction ledger and idempotent
# notification processing are silently disabled (see conf.py docstrings).
CREATEUS_BILLING_STORE_TRANSACTION_MODEL = "accounts.StoreTransaction"
CREATEUS_BILLING_STORE_NOTIFICATION_MODEL = "accounts.StoreNotification"

# Apple App Store — required
APPSTORE_BUNDLE_ID = "com.cookthis.pro"
APPSTORE_ISSUER_ID = config("APPSTORE_ISSUER_ID")          # App Store Connect → Users and Access → Integrations → In-App Purchase
APPSTORE_KEY_ID = config("APPSTORE_KEY_ID")                  # same page, the key you generate
APPSTORE_PRIVATE_KEY = config("APPSTORE_PRIVATE_KEY")        # contents of the downloaded SubscriptionKey_XXXX.p8
APPSTORE_ROOT_CERTIFICATE_PATHS = [BASE_DIR / "secrets/apple/AppleRootCA-G3.cer"]
APPSTORE_ENVIRONMENT = config("APPSTORE_ENVIRONMENT", default="sandbox")  # "sandbox" | "production"

# Required once APPSTORE_ENVIRONMENT == "production"
APPSTORE_APP_APPLE_ID = config("APPSTORE_APP_APPLE_ID", cast=int, default=None)
```

Download Apple's current root CA certificates from
<https://www.apple.com/certificateauthority/> ("Apple Root CA - G3" as of
2024) and commit the `.cer` file path into your secrets/deploy setup — the
shared library never vendors these bytes itself, since verification is only
meaningful against certificates each project fetched and pinned itself.

The App Store Connect API key (`.p8`) is generated once per team under
**Users and Access → Integrations → In-App Purchase** and can sign for
every app in that team — one key works across CookThis, PocketTax,
PocketLaw, and DoctorGuwol (only `APPSTORE_BUNDLE_ID` differs per app).

### Concrete project setup

```python
# accounts/models.py
from django.conf import settings
from django.db import models

from createus_common.billing.models import (
    AbstractStoreNotification,
    AbstractStoreTransaction,
    AbstractUserSubscription,
)


class UserSubscription(AbstractUserSubscription):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription"
    )


class StoreTransaction(AbstractStoreTransaction):
    pass


class StoreNotification(AbstractStoreNotification):
    pass
```

```python
# accounts/admin.py
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
```

```python
# config/urls.py (or wherever your project mounts its API routes)
urlpatterns = [
    ...,
    path("account/subscription/", include("createus_common.billing.urls")),
]
```

That's it for endpoints — this yields:

```
POST /account/subscription/app-store/activate/        (IsAuthenticated)
POST /account/subscription/app-store/notifications/    (AllowAny — Apple calls this)
```

### Reacting to lifecycle changes (feature gating, cached flags, etc.)

`createus_common.billing` doesn't know about your `Plan`/feature-gating
model, so it fires signals instead — connect a receiver where your app's
`AppConfig.ready()` runs:

```python
# accounts/apps.py
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"

    def ready(self):
        from createus_common.billing import signals

        def on_activated(sender, subscription, **kwargs):
            # e.g. bust a cached "is_pro" flag, send an analytics event
            ...

        signals.subscription_activated.connect(on_activated)
        signals.subscription_renewed.connect(on_activated)
        signals.subscription_revoked.connect(_on_lost_access)
        signals.subscription_expired.connect(_on_lost_access)
```

Or just read `subscription.has_entitlement` directly wherever you gate a
feature — it already accounts for grace period correctly (see
`AbstractUserSubscription.has_entitlement` in
`createus_common/billing/models/subscriptions.py`).

### App Store Connect webhook setup

In App Store Connect: **App Information → App Store Server Notifications**,
set both the Production and Sandbox Server URLs to:

```
https://your-domain.example.com/account/subscription/app-store/notifications/
```

Use `AppleAppStoreProvider().request_test_notification()` (or
`python manage.py shell`) to have Apple send a `TEST` notification and
confirm delivery before going live.

### Reconciliation (background sync)

```
python manage.py sync_appstore_subscriptions
```

Run daily (cron, Celery beat, Cloud Scheduler — whatever the project
already uses). Notifications are the primary sync path; this is a safety
net for a missed/delayed delivery, not the main pipeline.

### iOS client contract

The client only ever sends `signed_transaction_info` — StoreKit 2's
`Transaction.jwsRepresentation` — to
`POST .../app-store/activate/`. The same call handles both the
initial-purchase flow and "Restore Purchases"; there is no separate restore
endpoint because StoreKit hands you the same kind of signed transaction
either way. **Never send a plan name, a boolean, or a bare transaction id**
— the server has nothing to verify against in that case.

### Google Play extensibility

`createus_common.billing.providers.base.AbstractStoreProvider` is the seam:
a future `createus_common.billing.providers.google` package implements the
same four methods (`verify_and_decode_transaction`,
`verify_and_decode_renewal_info`, `verify_and_decode_notification`,
`get_subscription_statuses`) against the Google Play Developer API + Real-time
Developer Notifications, returning the same `NormalizedTransaction` /
`NormalizedRenewalInfo` / `NormalizedNotification` / `StoreSubscriptionState`
dataclasses. `services.entitlement.AbstractEntitlementService` and the
`AbstractUserSubscription` model fields are already provider-agnostic — no
schema or state-machine changes are expected to be needed, only a new
provider + a thin `GoogleSubscriptionSyncService` mirroring
`services/apple.py`.

### Security rules

- **Never accept a plan/boolean/status from the client.** The only client
  input is a signed transaction JWS; everything else is derived
  server-side from Apple's own API response.
- **Always re-verify, never just decode.** `SignedDataVerifier` checks the
  x5c certificate chain against Apple's pinned root CA on every call — a
  payload that merely *looks* like a JWS (right shape, wrong/no valid
  signature) is rejected with `TransactionVerificationException`.
- **The activation endpoint always calls the live API**, even though the
  submitted JWS is itself verified — this is what prevents replay of a
  stale-but-validly-signed transaction from a lapsed subscription.
- **Cross-account hijack is rejected, not silently reassigned.**
  `AbstractEntitlementService.get_or_create_for_user` raises
  `SubscriptionException` if the submitted subscription's
  `original_transaction_id` is already linked to a different user.
- **Notifications are deduplicated by `notificationUUID`.** Configure
  `CREATEUS_BILLING_STORE_NOTIFICATION_MODEL` in production; without it,
  Apple's retried deliveries are reprocessed (and re-fire signals) every
  time.
