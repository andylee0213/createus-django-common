# filename: createus_common/auth/views.py

from django.contrib.auth import get_user_model

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from createus_common.auth.models import (
    EmailVerificationCodeType,
)
from createus_common.auth.serializers import (
    EmailCodeRequestSerializer,
    EmailCodeVerifySerializer,
)
from createus_common.auth.services.email_code_service import (
    EmailCodeService,
)
from createus_common.auth.services.resend_service import (
    ResendService,
)
from createus_common.auth.services.token_service import (
    TokenService,
)


User = get_user_model()


class BaseEmailCodeRequestView(APIView):

    email_subject = "Your verification code"

    email_sender = "contact@createusinc.com"

    email_brand_name = "Createus"

    code_type = EmailVerificationCodeType.LOGIN

    def get_email_html(
        self,
        code,
    ):
        return f"""
        <h2>{self.email_brand_name}</h2>
        <p>Your verification code is:</p>
        <h1>{code}</h1>
        """

    def post(self, request):
        serializer = EmailCodeRequestSerializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        email = serializer.validated_data["email"]

        verification = EmailCodeService.create_code(
            email=email,
            code_type=self.code_type,
        )

        ResendService.send_email(
            from_email=self.email_sender,
            to_email=email,
            subject=self.email_subject,
            html=self.get_email_html(
                verification.code,
            ),
        )

        return Response(
            {
                "success": True,
            },
            status=status.HTTP_200_OK,
        )


class BaseEmailCodeVerifyView(APIView):

    def get_or_create_user(
        self,
        email,
    ):
        user, _ = User.objects.get_or_create(
            username=email,
            defaults={
                "email": email,
            }
        )

        return user

    def post(self, request):
        serializer = EmailCodeVerifySerializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]

        verification = EmailCodeService.verify_code(
            email=email,
            code=code,
        )

        if not verification:
            return Response(
                {
                    "success": False,
                    "message": "Invalid or expired code.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = self.get_or_create_user(email)

        token = TokenService.issue_token(user)

        return Response(
            {
                "success": True,
                "token": token.key,
                "user_id": user.id,
            },
            status=status.HTTP_200_OK,
        )
