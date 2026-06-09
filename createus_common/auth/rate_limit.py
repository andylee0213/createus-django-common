# filename: createus_common/auth/rate_limit.py

from django.conf import settings
from django.core.cache import cache


# ── Configurable limits ────────────────────────────────────────────────────
#
# Override any of these in your project's settings.py:
#
#   CREATEUS_AUTH_OTP_REQUEST_LIMIT          = 5    # max sends per email per window
#   CREATEUS_AUTH_OTP_REQUEST_WINDOW_SECONDS = 600  # 10 minutes
#   CREATEUS_AUTH_OTP_IP_REQUEST_LIMIT          = 20   # max sends per IP per window
#   CREATEUS_AUTH_OTP_IP_REQUEST_WINDOW_SECONDS = 3600 # 1 hour
#   CREATEUS_AUTH_OTP_VERIFY_FAILURE_LIMIT   = 5    # max failed verifies before block
#   CREATEUS_AUTH_OTP_VERIFY_BLOCK_SECONDS   = 900  # 15 minutes

def _cfg(name, default):
    return getattr(settings, name, default)


def _get_client_ip(request) -> str:
    """Return the real client IP, honouring X-Forwarded-For for reverse proxies."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or "unknown"


def _incr(key: str, timeout: int) -> int:
    """
    Atomically increment a cache counter, creating it with *timeout* if absent.

    Uses cache.add() (SET NX — atomic on Redis) then cache.incr() (INCR —
    atomic on Redis). Handles the race where the key expires between the two
    calls by restarting the window.
    """
    if cache.add(key, 1, timeout):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        # Key expired between add() and incr() — restart window
        cache.set(key, 1, timeout)
        return 1


def check_otp_request_rate(request, email: str) -> tuple[bool, str]:
    """
    Check and record an OTP send attempt for *email* from *request*.

    Enforces two independent rate limits:
      - Per-email: prevents a single address from being flooded.
      - Per-IP:    prevents a single client from rotating through many emails.

    Call this immediately before sending the code — the counter is incremented
    on every call, whether or not the send ultimately succeeds.

    Returns:
        (True, "")                      — allowed, proceed with send
        (False, "<safe reason string>") — blocked, return reason to caller
    """
    normalized = email.strip().lower()

    email_limit = _cfg("CREATEUS_AUTH_OTP_REQUEST_LIMIT", 5)
    email_window = _cfg("CREATEUS_AUTH_OTP_REQUEST_WINDOW_SECONDS", 600)
    ip_limit = _cfg("CREATEUS_AUTH_OTP_IP_REQUEST_LIMIT", 20)
    ip_window = _cfg("CREATEUS_AUTH_OTP_IP_REQUEST_WINDOW_SECONDS", 3600)

    email_count = _incr(f"createus:otp_req_email:{normalized}", email_window)
    ip_count = _incr(f"createus:otp_req_ip:{_get_client_ip(request)}", ip_window)

    if email_count > email_limit:
        return False, "Too many code requests. Please try again later."
    if ip_count > ip_limit:
        return False, "Too many requests from this network. Please try again later."
    return True, ""


def is_otp_verify_blocked(request, email: str) -> tuple[bool, str]:
    """
    Check whether *email* has exceeded the failed-verification limit.

    Does NOT increment any counter — purely a read. Call this before
    attempting verification so you can reject early without wasting
    a database query.

    Returns:
        (True,  "<safe reason string>") — blocked
        (False, "")                     — not blocked, proceed
    """
    limit = _cfg("CREATEUS_AUTH_OTP_VERIFY_FAILURE_LIMIT", 5)
    count = cache.get(f"createus:otp_verify_fail:{email.strip().lower()}", 0)
    if count >= limit:
        return True, "Too many failed attempts. Please request a new code."
    return False, ""


def record_otp_verify_failure(request, email: str) -> None:
    """
    Increment the failed-verification counter for *email*.

    Call this every time a submitted code does not match or is expired.
    The counter expires after CREATEUS_AUTH_OTP_VERIFY_BLOCK_SECONDS.
    """
    block_seconds = _cfg("CREATEUS_AUTH_OTP_VERIFY_BLOCK_SECONDS", 900)
    _incr(f"createus:otp_verify_fail:{email.strip().lower()}", block_seconds)
