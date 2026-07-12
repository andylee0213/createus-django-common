# filename: createus_common/auth/admin.py

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from createus_common.auth.models import EmailVerificationCode


@admin.register(EmailVerificationCode)
class EmailVerificationCodeAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "code",
        "code_type",
        "status",
        "is_expired_display",
        "failed_attempt_count",
        "created_at",
        "expires_at",
        "verified_at",
    )
    list_filter = (
        "code_type",
        "status",
    )
    search_fields = (
        "email",
        "code",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    readonly_fields = (
        "email",
        "code",
        "code_type",
        "status",
        "expires_at",
        "verified_at",
        "failed_attempt_count",
        "metadata",
        "created_at",
        "updated_at",
    )

    @admin.display(boolean=True, description=_("Expired"))
    def is_expired_display(self, obj):
        return obj.is_expired

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
