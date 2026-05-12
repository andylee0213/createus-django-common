# filename: createus_common/auth/services/email_code_service.py

from datetime import timedelta

from django.utils import timezone

from createus_common.auth.models import (
    EmailVerificationCode,
    EmailVerificationCodeStatus,
)
from createus_common.auth.utils.code_generator import (
    generate_verification_code,
)


class EmailCodeService:

    CODE_EXPIRE_MINUTES = 10

    @classmethod
    def create_code(
        cls,
        email,
        code_type,
        metadata=None,
    ):
        cls.expire_previous_codes(email)

        code = generate_verification_code()

        verification = EmailVerificationCode.objects.create(
            email=email,
            code=code,
            code_type=code_type,
            expires_at=timezone.now() + timedelta(
                minutes=cls.CODE_EXPIRE_MINUTES
            ),
            metadata=metadata or {},
        )

        return verification

    @classmethod
    def expire_previous_codes(cls, email):
        pending_codes = EmailVerificationCode.objects.filter(
            email=email,
            status=EmailVerificationCodeStatus.PENDING,
        )

        for code in pending_codes:
            code.mark_expired()

    @classmethod
    def verify_code(
        cls,
        email,
        code,
    ):
        verification = (
            EmailVerificationCode.objects
            .filter(
                email=email,
                code=code,
                status=EmailVerificationCodeStatus.PENDING,
            )
            .order_by("-created")
            .first()
        )

        if not verification:
            return None

        if verification.is_expired:
            verification.mark_expired()
            return None

        verification.mark_verified()

        return verification
