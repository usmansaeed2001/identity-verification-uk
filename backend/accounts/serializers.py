from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from common.permissions import is_reviewer

User = get_user_model()


class MeSerializer(serializers.ModelSerializer):
    email_verified = serializers.BooleanField(read_only=True)
    is_reviewer = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "email_verified", "is_staff", "is_reviewer"]

    def get_is_reviewer(self, user) -> bool:
        return is_reviewer(user)


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists. Sign in instead.")
        return value

    def validate(self, attrs):
        try:
            validate_password(attrs["password"], User(email=attrs["email"]))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True)
