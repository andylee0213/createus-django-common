# filename: createus_common/auth/views.py

import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from createus_common.auth.models import EmailVerificationCodeType
from createus_common.auth.serializers import (
    EmailCodeRequestSerializer,
    EmailCodeVerifySerializer,
)
from createus_common.auth.services.email_code_service import EmailCodeService
from createus_common.auth.services.resend_service import ResendService
from createus_common.auth.services.token_service import TokenService


def _setting(name, default):
    return getattr(settings, name, default)


class BaseEmailCodeRequestView(APIView):
    """
    Base view for OTP email code requests.

    Configuration (class attribute → project settings → hardcoded default):

        class MyView(BaseEmailCodeRequestView):
            email_brand_name = "MyApp"   # highest priority
            email_subject    = "Login to MyApp"
            email_sender     = "MyApp <noreply@myapp.com>"

    Project-wide defaults via settings.py:

        CREATEUS_AUTH_DEFAULT_BRAND_NAME = "MyApp"
        CREATEUS_AUTH_EMAIL_SUBJECT      = "Your verification code"
        CREATEUS_AUTH_EMAIL_SENDER       = "MyApp <noreply@example.com>"
    """

    # Set to None so the resolution chain (class attr → settings → hardcoded)
    # works correctly. Subclasses override by assigning a non-None string.
    email_brand_name = None
    email_subject = None
    email_sender = None
    code_type = EmailVerificationCodeType.LOGIN

    # ── Configuration resolution ─────────────────────────────────────────────

    def get_email_brand_name(self) -> str:
        return (
            self.email_brand_name
            or _setting("CREATEUS_AUTH_DEFAULT_BRAND_NAME", "Createus")
        )

    def get_email_subject(self) -> str:
        return (
            self.email_subject
            or _setting("CREATEUS_AUTH_EMAIL_SUBJECT", "Your verification code")
        )

    def get_email_sender(self) -> str:
        return (
            self.email_sender
            or _setting("CREATEUS_AUTH_EMAIL_SENDER", "Createus <noreply@createusinc.com>")
        )

    # ── Email body ───────────────────────────────────────────────────────────

    def get_email_html(self, code: str) -> str:
        brand = self.get_email_brand_name()
        return f"""
        <h2>{brand}</h2>
        <p>Your verification code is:</p>
        <h1 style="letter-spacing:4px">{code}</h1>
        <p style="color:#666;font-size:13px">This code expires in 10 minutes.</p>
        """

    # ── Request handler ──────────────────────────────────────────────────────

    def post(self, request):
        serializer = EmailCodeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        verification = EmailCodeService.create_code(
            email=email,
            code_type=self.code_type,
        )

        ResendService.send_email(
            from_email=self.get_email_sender(),
            to_email=email,
            subject=self.get_email_subject(),
            html=self.get_email_html(verification.code),
        )

        return Response({"success": True}, status=status.HTTP_200_OK)


class BaseEmailCodeVerifyView(APIView):
    """
    Base view for OTP email code verification.

    Override get_or_create_user() to customize user creation behaviour
    (e.g. to set extra profile fields on first login).

    The default implementation:
      1. Looks up an existing user by case-insensitive email (active first).
      2. Returns that user if found — no duplicate creation.
      3. Creates a new user only when no match exists, with a collision-safe
         username derived from the email local-part + uuid4 suffix.
    """

    def get_or_create_user(self, email: str):
        User = get_user_model()
        normalized = email.strip().lower()

        # 1. Prefer an existing active user
        user = (
            User.objects.filter(email__iexact=normalized, is_active=True)
            .order_by("date_joined")
            .first()
        )
        if user:
            return user

        # 2. Accept any matching user (including inactive) — let the caller decide
        user = (
            User.objects.filter(email__iexact=normalized)
            .order_by("date_joined")
            .first()
        )
        if user:
            return user

        # 3. Create — username = email local-part, with uuid suffix on collision
        base_username = normalized.split("@")[0][:100]
        try:
            return User.objects.create_user(username=base_username, email=normalized)
        except IntegrityError:
            username = f"{base_username}_{uuid.uuid4().hex[:8]}"
            return User.objects.create_user(username=username, email=normalized)

    def post(self, request):
        serializer = EmailCodeVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]

        verification = EmailCodeService.verify_code(email=email, code=code)

        if not verification:
            return Response(
                {"success": False, "message": "Invalid or expired code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = self.get_or_create_user(email)
        token = TokenService.issue_token(user)

        return Response(
            {"success": True, "token": token.key, "user_id": user.id},
            status=status.HTTP_200_OK,
        )
