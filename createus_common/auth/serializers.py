# filename: createus_common/auth/serializers.py

from rest_framework import serializers


class EmailCodeRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EmailCodeVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()

    code = serializers.CharField(
        max_length=10,
    )
