from django.core.exceptions import ImproperlyConfigured

from config.settings.base import *  # noqa: F403
from config.settings.base import DEV_ENCRYPTION_KEY, DEV_SECRET_KEY, env

DEBUG = False
SESSION_COOKIE_SECURE = env.bool("SECURE_COOKIES", default=True)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

_insecure = []
if SECRET_KEY == DEV_SECRET_KEY:  # noqa: F405
    _insecure.append("SECRET_KEY")
if DEV_ENCRYPTION_KEY in DATA_ENCRYPTION_KEYS:  # noqa: F405
    _insecure.append("DATA_ENCRYPTION_KEYS")
if _insecure:
    raise ImproperlyConfigured(f"Set real values for these settings in production: {', '.join(_insecure)}")
