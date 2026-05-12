# filename: createus_common/auth/urls.py

from django.urls import path

from createus_common.auth.views import (
    BaseEmailCodeRequestView,
    BaseEmailCodeVerifyView,
)

urlpatterns = [
    path(
        "request-code/",
        BaseEmailCodeRequestView.as_view(),
    ),
    path(
        "verify-code/",
        BaseEmailCodeVerifyView.as_view(),
    ),
]
