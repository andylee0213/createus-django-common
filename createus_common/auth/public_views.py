# filename: createus_common/auth/public_views.py

from rest_framework.permissions import AllowAny

from createus_common.auth.views import (
    BaseEmailCodeRequestView,
    BaseEmailCodeVerifyView,
)


class PublicEmailCodeRequestView(BaseEmailCodeRequestView):
    """
    Ready-to-use OTP request view open to unauthenticated users.

    Eliminates the boilerplate of setting AllowAny in every project.
    Use directly in urls.py or subclass to configure brand/subject/sender:

        # Direct usage — inherits Createus defaults
        path("auth/request-code/", PublicEmailCodeRequestView.as_view()),

        # Project-branded subclass
        class EmailCodeRequestView(PublicEmailCodeRequestView):
            email_brand_name = "PocketLaw"
            email_subject    = "PocketLaw 인증 코드"
    """

    permission_classes = [AllowAny]


class PublicEmailCodeVerifyView(BaseEmailCodeVerifyView):
    """
    Ready-to-use OTP verify view open to unauthenticated users.

    Eliminates the boilerplate of setting AllowAny in every project.
    Use directly in urls.py or subclass to override get_or_create_user():

        # Direct usage
        path("auth/verify-code/", PublicEmailCodeVerifyView.as_view()),

        # Project-specific user creation
        class EmailCodeVerifyView(PublicEmailCodeVerifyView):
            def get_or_create_user(self, email):
                # custom logic
                ...
    """

    permission_classes = [AllowAny]
