# filename: createus_common/messaging/models.py

from django.conf import settings
from django.db import models

from createus_common.models import TimeStampedModel
from .choices import SenderRole


class AbstractMessageThread(TimeStampedModel):
    """
    Reusable conversation container.

    Concrete projects must add participant FKs and any domain-specific
    parent reference (case, matter, order, etc.).
    """

    title = models.CharField(max_length=255, blank=True)
    is_archived = models.BooleanField(default=False)
    last_message_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True
        ordering = ["-last_message_at", "-created_at"]


class AbstractThreadMessage(TimeStampedModel):
    """
    Reusable message row.

    Concrete projects must add a FK to their thread model:
        thread = models.ForeignKey(MyThread, on_delete=models.CASCADE, related_name="messages")
    """

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    sender_role = models.IntegerField(choices=SenderRole.choices)
    content = models.TextField(blank=True)
    is_internal = models.BooleanField(default=False)
    is_read_by_staff = models.BooleanField(default=False)
    is_read_by_client = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True
        ordering = ["created_at"]


class AbstractMessageAttachment(TimeStampedModel):
    """
    Reusable attachment metadata row.

    Storage is intentionally omitted — concrete projects choose their own
    storage backend (FileField, S3 key, GCS URI, CDN URL, etc.) and add it
    as an additional field.

    Concrete projects must add a FK to their message model:
        message = models.ForeignKey(MyMessage, on_delete=models.CASCADE, related_name="attachments")
    """

    filename = models.CharField(max_length=500)
    file_size = models.BigIntegerField(default=0)
    content_type = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True
