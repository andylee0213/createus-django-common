# filename: createus_common/auth/backends.py

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


def _pick_best_user(candidates):
    """
    From a list of users sharing an email address, return the most appropriate
    one using a deterministic priority chain:

    1. Active users are preferred over inactive.
    2. Among active (or all, if none are active), prefer the one with the most
       recent last_login — they are the account in actual use.
    3. If no one has ever logged in, prefer the oldest account (smallest
       date_joined) — the original registration.
    4. Final tiebreaker: smallest pk.

    This handles legacy duplicate-email states without blocking login entirely.
    Once duplicates are merged the list will always have exactly one entry.
    """
    active = [u for u in candidates if u.is_active]
    pool = active if active else candidates

    logged_in = [u for u in pool if u.last_login is not None]
    if logged_in:
        return max(logged_in, key=lambda u: (u.last_login, -u.pk))

    return min(pool, key=lambda u: (u.date_joined, u.pk))


class EmailOrUsernameBackend(ModelBackend):
    """
    Project-agnostic authentication backend for Createus projects.

    Resolution order:
      1. Case-insensitive email lookup.  If multiple users share the email,
         _pick_best_user() resolves deterministically (active → recent login →
         oldest join → smallest pk).
      2. Exact username match, as a fallback for accounts created before
         email-based login was introduced.

    Inactive users are rejected at the user_can_authenticate() check inherited
    from ModelBackend — no special handling needed here.

    Usage (settings.py):
        AUTHENTICATION_BACKENDS = [
            "createus_common.auth.backends.EmailOrUsernameBackend",
            "django.contrib.auth.backends.ModelBackend",
        ]
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        User = get_user_model()
        credential = username.strip()

        # 1. Email lookup (case-insensitive)
        candidates = list(User.objects.filter(email__iexact=credential))
        if candidates:
            user = _pick_best_user(candidates)
        else:
            # 2. Username fallback
            try:
                user = User.objects.get(username=credential)
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
