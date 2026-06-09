# filename: createus_common/auth/urls.py

from django.urls import path

from createus_common.auth.public_views import (
    PublicEmailCodeRequestView,
    PublicEmailCodeVerifyView,
)

urlpatterns = [
    path(
        "request-code/",
        PublicEmailCodeRequestView.as_view(),
        name="createus_auth_request_code",
    ),
    path(
        "verify-code/",
        PublicEmailCodeVerifyView.as_view(),
        name="createus_auth_verify_code",
    ),
]
