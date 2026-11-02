from django.core import signing

EMAIL_VERIFY_SALT = "accounts.email-verify"
EMAIL_VERIFY_MAX_AGE = 60 * 60 * 24 * 3


def make_email_token(user) -> str:
    return signing.dumps({"uid": user.pk, "email": user.email}, salt=EMAIL_VERIFY_SALT)


def read_email_token(token: str) -> dict | None:
    try:
        return signing.loads(token, salt=EMAIL_VERIFY_SALT, max_age=EMAIL_VERIFY_MAX_AGE)
    except signing.BadSignature:
        return None
