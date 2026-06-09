# filename: createus_common/messaging/utils.py

from django.utils import timezone

from .choices import MessageReadTarget, SenderRole


def mark_messages_read(queryset, target: MessageReadTarget) -> int:
    if target == MessageReadTarget.STAFF:
        return queryset.filter(is_read_by_staff=False).update(is_read_by_staff=True)
    if target == MessageReadTarget.CLIENT:
        return queryset.filter(is_read_by_client=False).update(is_read_by_client=True)
    if target == MessageReadTarget.BOTH:
        updated = queryset.filter(is_read_by_staff=False).update(is_read_by_staff=True)
        updated += queryset.filter(is_read_by_client=False).update(is_read_by_client=True)
        return updated
    return 0


def get_unread_count(queryset, target: MessageReadTarget) -> int:
    if target == MessageReadTarget.STAFF:
        return queryset.filter(is_read_by_staff=False).count()
    if target == MessageReadTarget.CLIENT:
        return queryset.filter(is_read_by_client=False).count()
    return 0


def filter_visible_messages(queryset, sender_role: int):
    if sender_role == SenderRole.CLIENT:
        return queryset.filter(is_internal=False)
    return queryset


def update_thread_timestamp(thread, message_time=None) -> None:
    """
    Set thread.last_message_at to message_time (or now) and save only that field.

    Uses update_fields for efficiency — avoids touching unrelated fields and
    prevents race conditions from a full model save.
    """
    thread.last_message_at = message_time or timezone.now()
    thread.save(update_fields=["last_message_at"])
