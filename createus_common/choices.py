# filename: createus_common/choices.py

from django.db import models


class LanguageChoice(models.IntegerChoices):
    KO = 1, "Korean"
    EN = 2, "English"
    ZH_HANT = 3, "Traditional Chinese"

    @property
    def code(self):
        if self == LanguageChoice.KO:
            return "ko"

        if self == LanguageChoice.EN:
            return "en"

        if self == LanguageChoice.ZH_HANT:
            return "zh-hant"

        return "ko"

    @classmethod
    def to_code(cls, value):
        if value is None:
            return None

        try:
            return cls(value).code
        except ValueError:
            return None
