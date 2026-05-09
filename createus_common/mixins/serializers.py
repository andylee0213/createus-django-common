from decimal import Decimal, ROUND_HALF_UP
from rest_framework import serializers


class CustomDecimalField(serializers.DecimalField):
    def to_internal_value(self, data):
        try:
            quantize_value = Decimal(10) ** -self.decimal_places
            rounded_value = Decimal(data).quantize(quantize_value, rounding=ROUND_HALF_UP)

            if len(rounded_value.as_tuple().digits) > self.max_digits:
                raise serializers.ValidationError(
                    f"Ensure that there are no more than {self.max_digits} digits in total."
                )
            return rounded_value
        except Exception as e:
            raise serializers.ValidationError(f"Invalid decimal value: {e}")


class DecimalFieldValidationMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            if isinstance(field, serializers.DecimalField):
                self.fields[field_name] = CustomDecimalField(
                    max_digits=field.max_digits,
                    decimal_places=field.decimal_places,
                    required=field.required,
                    allow_null=field.allow_null,
                    default=field.default,
                )
