from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts import emails
from accounts.serializers import (
    EmailSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    RegisterSerializer,
    TokenSerializer,
)
from accounts.tokens import read_email_token

User = get_user_model()


@method_decorator(csrf_protect, name="dispatch")
class AuthThrottled(APIView):
    """DRF only checks CSRF for signed-in users; these views need it before sign-in too."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """The React app calls this once so Django sets the csrftoken cookie."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"ok": True})


class MeView(APIView):
    def get(self, request):
        return Response(MeSerializer(request.user).data)


class RegisterView(AuthThrottled):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.create_user(serializer.validated_data["email"], serializer.validated_data["password"])
        login(request, user)
        emails.send_verification_email(user)
        return Response(MeSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(AuthThrottled):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            email=serializer.validated_data["email"].strip().lower(),
            password=serializer.validated_data["password"],
        )
        if user is None:
            raise AuthenticationFailed("That email and password don't match an account.")
        login(request, user)
        return Response(MeSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response({"ok": True})


class VerifyEmailView(AuthThrottled):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = read_email_token(serializer.validated_data["token"])
        user = User.objects.filter(pk=data["uid"], email=data["email"]).first() if data else None
        if user is None:
            raise ValidationError({"token": ["That link has expired or isn't valid. Ask for a new one."]})
        if not user.email_verified:
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at"])
        return Response({"ok": True})


class ResendVerificationView(AuthThrottled):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.email_verified:
            emails.send_verification_email(request.user)
        return Response({"ok": True})


class PasswordResetView(AuthThrottled):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"], is_active=True).first()
        if user:
            emails.send_password_reset_email(user)
        # Same answer either way, so the form can't be used to find out who has an account.
        return Response({"ok": True})


class PasswordResetConfirmView(AuthThrottled):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pk = force_str(urlsafe_base64_decode(serializer.validated_data["uid"]))
            user = User.objects.get(pk=pk)
        except (ValueError, TypeError, OverflowError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, serializer.validated_data["token"]):
            raise ValidationError({"token": ["That reset link has expired or was already used. Ask for a new one."]})
        try:
            validate_password(serializer.validated_data["password"], user)
        except DjangoValidationError as exc:
            raise ValidationError({"password": exc.messages}) from exc
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])
        return Response({"ok": True})
