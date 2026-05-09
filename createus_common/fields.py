from decimal import Decimal, ROUND_HALF_UP
from django.db import models


class RoundedDecimalField(models.DecimalField):
    def to_python(self, value):
        res = super().to_python(value)
        if res is None:
            return res
        return self.round_value(res)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return value
        return self.round_value(value)

    def round_value(self, value):
        decimal_value = Decimal(value)
        return decimal_value.quantize(Decimal(10) ** -self.decimal_places, rounding=ROUND_HALF_UP)
