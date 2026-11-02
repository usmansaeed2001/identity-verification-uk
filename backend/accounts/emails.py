"""Emails to drivers. They carry a first name and a link at most: never codes or check results."""

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.tokens import make_email_token

logger = logging.getLogger(__name__)


def _send(to: str, subject: str, body: str) -> None:
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to])
    except Exception:  # a mail outage mustn't break sign-up or a review decision
        logger.exception("Couldn't send '%s' email", subject)


def send_verification_email(user) -> None:
    link = f"{settings.FRONTEND_URL}/verify-email?token={make_email_token(user)}"
    _send(
        user.email,
        "Confirm your email address",
        f"Hello,\n\nConfirm your email address to carry on with your driver application:\n\n{link}\n\n"
        "The link works for 3 days. If you didn't sign up, ignore this email.\n",
    )


def send_password_reset_email(user) -> None:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    _send(
        user.email,
        "Reset your password",
        f"Hello,\n\nReset your password here:\n\n{link}\n\nIf you didn't ask for this, ignore this email.\n",
    )


def send_driver_update(user, subject: str, message: str) -> None:
    _send(
        user.email,
        subject,
        f"Hello,\n\n{message}\n\nSign in to see your application: {settings.FRONTEND_URL}/\n",
    )
