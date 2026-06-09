# Createus Authentication

Shared, reusable authentication for all Createus projects.

Covers:
- OTP email code login (passwordless)
- Password login via `EmailOrUsernameBackend`
- OTP rate limiting
- Token issuance (DRF `authtoken`)

---

## Package layout

```
createus_common/auth/
  apps.py               AppConfig (label: createus_auth)
  backends.py           EmailOrUsernameBackend
  models.py             EmailVerificationCode
  rate_limit.py         check_otp_request_rate / is_otp_verify_blocked / record_otp_verify_failure
  serializers.py        EmailCodeRequestSerializer / EmailCodeVerifySerializer
  public_views.py       PublicEmailCodeRequestView / PublicEmailCodeVerifyView  ← use these in urls.py
  views.py              BaseEmailCodeRequestView / BaseEmailCodeVerifyView       ← subclass for customisation
  urls.py               default URL patterns (uses public views)
  services/
    email_code_service.py   create_code / verify_code / expire_previous_codes
    resend_service.py       ResendService.send_email
    token_service.py        TokenService.issue_token
  utils/
    code_generator.py       generate_verification_code
```

---

## 1. settings.py integration

```python
INSTALLED_APPS = [
    # ...
    "rest_framework",
    "rest_framework.authtoken",
    "createus_common",
    "createus_common.auth.apps.CreateusAuthConfig",
]

AUTHENTICATION_BACKENDS = [
    "createus_common.auth.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Required
RESEND_API_KEY = env("RESEND_API_KEY")

# Optional — override Createus defaults
CREATEUS_AUTH_DEFAULT_BRAND_NAME        = "My App"
CREATEUS_AUTH_EMAIL_SUBJECT             = "Your verification code"
CREATEUS_AUTH_EMAIL_SENDER              = "My App <noreply@myapp.com>"

# OTP rate limit tuning (optional — shown with defaults)
CREATEUS_AUTH_OTP_REQUEST_LIMIT              = 5     # max sends per email per window
CREATEUS_AUTH_OTP_REQUEST_WINDOW_SECONDS     = 600   # 10 minutes
CREATEUS_AUTH_OTP_IP_REQUEST_LIMIT           = 20    # max sends per IP per window
CREATEUS_AUTH_OTP_IP_REQUEST_WINDOW_SECONDS  = 3600  # 1 hour
CREATEUS_AUTH_OTP_VERIFY_FAILURE_LIMIT       = 5     # max failed verifies before block
CREATEUS_AUTH_OTP_VERIFY_BLOCK_SECONDS       = 900   # 15 minutes
```

---

## 2. urls.py integration

### Simplest — use the defaults directly

```python
# config/urls.py
from django.urls import include, path

urlpatterns = [
    path("api/auth/", include("createus_common.auth.urls")),
]
```

This wires up:
- `POST /api/auth/request-code/`
- `POST /api/auth/verify-code/`

### Project-branded views

```python
# myapp/auth_views.py
from createus_common.auth.public_views import (
    PublicEmailCodeRequestView,
    PublicEmailCodeVerifyView,
)

class EmailCodeRequestView(PublicEmailCodeRequestView):
    email_brand_name = "My App"
    email_subject    = "My App verification code"

class EmailCodeVerifyView(PublicEmailCodeVerifyView):
    pass  # override get_or_create_user() if needed
```

```python
# myapp/urls.py
from django.urls import path
from myapp.auth_views import EmailCodeRequestView, EmailCodeVerifyView

urlpatterns = [
    path("auth/request-code/", EmailCodeRequestView.as_view()),
    path("auth/verify-code/",  EmailCodeVerifyView.as_view()),
]
```

---

## 3. Email code login flow

```
Client                          Server
  │                               │
  │  POST /auth/request-code/     │
  │  { "email": "user@example.com" } ──▶ EmailCodeService.create_code()
  │                               │     ResendService.send_email()
  │  ◀── 200 { "success": true }  │
  │                               │
  │  POST /auth/verify-code/      │
  │  { "email": "...", "code": "123456" } ──▶ EmailCodeService.verify_code()
  │                               │            get_or_create_user()
  │                               │            TokenService.issue_token()
  │  ◀── 200 { "success": true,   │
  │            "token": "...",    │
  │            "user_id": 42 }    │
```

All subsequent requests use the DRF token:

```
Authorization: Token <token>
```

---

## 4. OTP rate limiting

Import and use in your views:

```python
from createus_common.auth.rate_limit import (
    check_otp_request_rate,
    is_otp_verify_blocked,
    record_otp_verify_failure,
)

# Before sending a code
allowed, reason = check_otp_request_rate(request, email)
if not allowed:
    return Response({"error": reason}, status=429)

# Before verifying a code
blocked, reason = is_otp_verify_blocked(request, email)
if blocked:
    return Response({"error": reason}, status=429)

# After a failed verify attempt
record_otp_verify_failure(request, email)
```

The public views (`PublicEmailCodeRequestView`, `PublicEmailCodeVerifyView`) do **not** enforce rate limiting by default — projects wire it into their own view layer so they control the HTTP response format and status codes.

---

## 5. Password login — EmailOrUsernameBackend

`EmailOrUsernameBackend` extends `ModelBackend` and accepts both email and username as the `username` credential.

### Duplicate email resolution

If multiple users share the same email (legacy state), the backend selects one deterministically:

| Priority | Rule |
|----------|------|
| 1 | Active users preferred over inactive |
| 2 | Most recent `last_login` (account in use) |
| 3 | Oldest `date_joined` (original registration) |
| 4 | Smallest `pk` (final tiebreaker) |

### Django admin compatibility

`EmailOrUsernameBackend` is listed before `ModelBackend`. The admin will use it first; `ModelBackend` catches anything not matched (e.g. superuser logins that predate email setup).

---

## 6. Custom user creation

Override `get_or_create_user()` on the verify view to attach profile data on first login:

```python
class EmailCodeVerifyView(PublicEmailCodeVerifyView):
    def get_or_create_user(self, email):
        user = super().get_or_create_user(email)
        # Ensure related profile exists
        MyProfile.objects.get_or_create(user=user)
        return user
```

---

## 7. PocketLaw migration example

**Before** (duplicated in `accounts/backends.py`, `accounts/rate_limit.py`, portal views):

```python
# portal/views.py — EmailCodeRequestView, EmailCodeVerifyView defined here
# accounts/backends.py — EmailOrUsernameBackend defined here
# accounts/rate_limit.py — check_otp_request_rate etc. defined here
```

**After** (no project-level auth code except branding):

```python
# pocketlaw/auth_views.py
from createus_common.auth.public_views import (
    PublicEmailCodeRequestView,
    PublicEmailCodeVerifyView,
)

class EmailCodeRequestView(PublicEmailCodeRequestView):
    email_brand_name = "PocketLaw"

class EmailCodeVerifyView(PublicEmailCodeVerifyView):
    email_brand_name = "PocketLaw"

    def get_or_create_user(self, email):
        user = super().get_or_create_user(email)
        # Create Client profile if needed
        from clients.models import Client
        Client.objects.get_or_create(user=user)
        return user
```

```python
# settings.py
AUTHENTICATION_BACKENDS = [
    "createus_common.auth.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Remove accounts.backends, accounts.rate_limit — replaced by common
```

---

## 8. PocketTax integration example

```python
# tax_platform/auth_views.py
from createus_common.auth.public_views import (
    PublicEmailCodeRequestView,
    PublicEmailCodeVerifyView,
)

class EmailCodeRequestView(PublicEmailCodeRequestView):
    email_brand_name = "PocketTax"
    email_subject    = "PocketTax 인증 코드"

class EmailCodeVerifyView(PublicEmailCodeVerifyView):
    email_brand_name = "PocketTax"
```

```python
# tax_platform/urls.py
from django.urls import path
from tax_platform.auth_views import EmailCodeRequestView, EmailCodeVerifyView

urlpatterns = [
    path("auth/request-code/", EmailCodeRequestView.as_view()),
    path("auth/verify-code/",  EmailCodeVerifyView.as_view()),
]
```

```python
# settings.py
AUTHENTICATION_BACKENDS = [
    "createus_common.auth.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

CREATEUS_AUTH_DEFAULT_BRAND_NAME = "PocketTax"
CREATEUS_AUTH_EMAIL_SENDER       = "PocketTax <noreply@pockettax.com>"
```

---

## 9. Cache backend requirement

`rate_limit.py` uses `django.core.cache.cache`. The default `LocMemCache` works for development but is not shared across processes. Use Redis in production:

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
    }
}
```
