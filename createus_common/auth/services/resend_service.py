# filename: createus_common/auth/services/resend_service.py

import resend

from django.conf import settings
from resend import Emails


resend.api_key = settings.RESEND_API_KEY


class ResendService:

    @classmethod
    def send_email(
        cls,
        from_email,
        to_email,
        subject,
        html,
    ):
        return Emails.send({
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
