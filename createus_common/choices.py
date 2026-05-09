# filename: common/choices.py

from django.db import models


class LanguageChoice(models.IntegerChoices):
    KO = 1, "Korean"
    EN = 2, "English"
    ZH_HANT = 3, "Traditional Chinese"
