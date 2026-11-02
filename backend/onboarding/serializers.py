from datetime import date

from rest_framework import serializers

from onboarding import validation
from onboarding.enums import DocumentType, Route
from providers import checksharecode


def _wrap(fn, value):
    try:
        return fn(value)
    except ValueError as exc:
        raise serializers.ValidationError(str(exc)) from exc


class ProfileSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    dob = serializers.DateField()
    phone = serializers.CharField(max_length=30)
    route = serializers.ChoiceField(choices=Route.choices)

    def validate_dob(self, value: date) -> date:
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18:
            raise serializers.ValidationError("You must be 18 or over to drive an HGV.")
        if age > 100:
            raise serializers.ValidationError("Check your date of birth.")
        return value

    def validate_phone(self, value: str) -> str:
        return _wrap(validation.validate_uk_mobile, value)


class ConsentSerializer(serializers.Serializer):
    data_consent = serializers.BooleanField()
    dvla_consent = serializers.BooleanField()

    def validate(self, attrs):
        if not (attrs["data_consent"] and attrs["dvla_consent"]):
            raise serializers.ValidationError("You need to agree to both to carry on.")
        return attrs


class DocumentSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=DocumentType.choices)
    front = serializers.ImageField(allow_empty_file=False)
    back = serializers.ImageField(required=False, allow_empty_file=False)


class ShareCodeSerializer(serializers.Serializer):
    share_code = serializers.CharField(max_length=20)
    dob = serializers.DateField(required=False)

    def validate_share_code(self, value: str) -> str:
        # Sandbox test codes (AA1AA1AA1...) don't start with W.
        return _wrap(
            lambda v: validation.validate_share_code(v, require_w_prefix=not checksharecode.is_sandbox()), value
        )


class LicenceSerializer(serializers.Serializer):
    licence_number = serializers.CharField(max_length=30)
    check_code = serializers.CharField(max_length=20)

    def validate_licence_number(self, value: str) -> str:
        return _wrap(validation.validate_licence_number, value)

    def validate_check_code(self, value: str) -> str:
        return _wrap(validation.validate_dvla_check_code, value)


class PhotoSerializer(serializers.Serializer):
    photo = serializers.ImageField(allow_empty_file=False)
