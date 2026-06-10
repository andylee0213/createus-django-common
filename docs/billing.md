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
