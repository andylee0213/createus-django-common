# filename: createus_common/billing/urls.py

"""
Include under whatever prefix a project likes, e.g. in the project's own
urls.py::

    path("account/subscription/", include("createus_common.billing.urls")),

which yields:

    POST /account/subscription/app-store/activate/
    POST /account/subscription/app-store/notifications/

Requires the ``apple`` extra (``pip install createus-django-common[apple]``)
and the settings documented in
``createus_common/billing/providers/apple/conf.py`` and
``createus_common/billing/conf.py``.
"""

from django.urls import path

from createus_common.billing.views import (
    AppStoreActivateSubscriptionView,
    AppStoreServerNotificationsView,
)

urlpatterns = [
    path(
        "app-store/activate/",
        AppStoreActivateSubscriptionView.as_view(),
        name="createus_billing_appstore_activate",
    ),
    path(
        "app-store/notifications/",
        AppStoreServerNotificationsView.as_view(),
        name="createus_billing_appstore_notifications",
    ),
]
