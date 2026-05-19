# filename: createus_common/billing/apps.py

from django.apps import AppConfig


class CreateusBillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "createus_common.billing"
    label = "createus_billing"
    verbose_name = "Createus Billing"
