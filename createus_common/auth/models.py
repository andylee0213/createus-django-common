# filename: createus_common/auth/models.py

from django.db import models
from django.utils import timezone

from createus_common.models import TimeStampedModel


class EmailVerificationCodeType(models.IntegerChoices):
    LOGIN = 1, "Login"
    SIGNUP = 2, "Signup"
    PASSWORD_RESET = 3, "Password Reset"


class EmailVerificationCodeStatus(models.IntegerChoices):
    PENDING = 1, "Pending"
    VERIFIED = 2, "Verified"
    EXPIRED = 3, "Expired"
    FAILED = 4, "Failed"


class EmailVerificationCode(TimeStampedModel):
    email = models.EmailField(db_index=True)

    code = models.CharField(
        max_length=10,
        db_index=True,
    )

    code_type = models.IntegerField(
        choices=EmailVerificationCodeType.choices,
        default=EmailVerificationCodeType.LOGIN,
    )

    status = models.IntegerField(
        choices=EmailVerificationCodeStatus.choices,
        default=EmailVerificationCodeStatus.PENDING,
    )

    expires_at = models.DateTimeField()

    verified_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    failed_attempt_count = models.PositiveIntegerField(default=0)

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email", "code"]),
            models.Index(fields=["email", "status"]),
        ]

    def __str__(self):
        return f"{self.email} ({self.code})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_verified(self):
        return self.status == EmailVerificationCodeStatus.VERIFIED

    @property
    def is_pending(self):
        return self.status == EmailVerificationCodeStatus.PENDING

    def mark_verified(self):
        self.status = EmailVerificationCodeStatus.VERIFIED
        self.verified_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "verified_at",
                "updated",
            ]
        )

    def mark_expired(self):
        self.status = EmailVerificationCodeStatus.EXPIRED
        self.save(
            update_fields=[
                "status",
                "updated",
            ]
        )

    def increment_failed_attempt(self):
        self.failed_attempt_count += 1
        self.save(
            update_fields=[
                "failed_attempt_count",
                "updated",
            ]
        )
