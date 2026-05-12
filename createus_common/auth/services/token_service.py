# filename: createus_common/auth/services/token_service.py

from rest_framework.authtoken.models import Token


class TokenService:

    @classmethod
    def issue_token(cls, user):
        token, _ = Token.objects.get_or_create(user=user)
        return token
