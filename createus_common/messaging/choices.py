# filename: createus_common/messaging/choices.py

from django.db import models


class SenderRole(models.IntegerChoices):
    CLIENT = 1, "Client"
    LAWYER = 2, "Lawyer"
    STAFF = 3, "Staff"
    SYSTEM = 4, "System"


class MessageVisibility(models.IntegerChoices):
    ALL = 1, "All"
    INTERNAL = 2, "Internal Only"


class MessageReadTarget(models.IntegerChoices):
    STAFF = 1, "Staff"
    CLIENT = 2, "Client"
    BOTH = 3, "Both"
