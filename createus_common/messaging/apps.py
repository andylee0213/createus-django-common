# filename: createus_common/messaging/apps.py

from django.apps import AppConfig


class CreateusMessagingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "createus_common.messaging"
    label = "createus_messaging"
    verbose_name = "Createus Messaging"
