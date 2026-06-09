# filename: createus_common/messaging/serializers.py

from rest_framework import serializers

from .choices import SenderRole


class AbstractMessageAttachmentSerializer(serializers.ModelSerializer):
    """
    Base serializer for attachment metadata.

    Concrete projects subclass this and set model + any storage-specific
    fields (e.g. file_url, download_url, s3_key).
    """

    class Meta:
        fields = [
            "id",
            "filename",
            "file_size",
            "content_type",
            "metadata",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
        ]


class AbstractThreadMessageSerializer(serializers.ModelSerializer):
    """
    Base serializer for thread messages.

    Concrete projects subclass this, set model, and optionally nest
    their own attachment serializer under the "attachments" field.
    """

    sender_role_display = serializers.SerializerMethodField()
    sender_name = serializers.SerializerMethodField()

    def get_sender_role_display(self, obj):
        try:
            return SenderRole(obj.sender_role).label
        except ValueError:
            return None

    def get_sender_name(self, obj):
        if obj.sender:
            return obj.sender.get_full_name() or obj.sender.get_username()
        return None

    class Meta:
        fields = [
            "id",
            "sender",
            "sender_name",
            "sender_role",
            "sender_role_display",
            "content",
            "is_internal",
            "is_read_by_staff",
            "is_read_by_client",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "sender",
            "sender_name",
            "sender_role",
            "sender_role_display",
            "is_read_by_staff",
            "is_read_by_client",
            "created_at",
            "updated_at",
        ]
