"""Settings shared by every environment. Values come from the environment or the repo-root .env file."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BASE_DIR.parent

env = environ.Env()
environ.Env.read_env(REPO_ROOT / ".env")

# Development-only secrets. config/settings/prod.py refuses to start with any of them.
DEV_SECRET_KEY = "dev-only-secret-key-do-not-use-in-production"
DEV_ENCRYPTION_KEY = "ZGV2LW9ubHkta2V5LWRvLW5vdC11c2UtaW4tcHJvZCE="

SECRET_KEY = env("SECRET_KEY", default=DEV_SECRET_KEY)
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "backend", ".trycloudflare.com"])
# Origins allowed to POST with the session cookie, e.g. the cloudflared URL for a phone demo.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=["http://localhost:5173", "http://localhost:8080", "https://*.trycloudflare.com"]
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
    "onboarding",
    "review",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://driver:driver@localhost:5433/driver_onboarding"),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7
CSRF_COOKIE_SAMESITE = "Lax"

# Uploads: photos are resized in the browser, so 8 MB is generous.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_RATES": {"auth": "10/min"},
    "EXCEPTION_HANDLER": "common.api.exception_handler",
}

CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Email: Mailpit catches everything in development (http://localhost:8025).
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Driver Onboarding <no-reply@driver-onboarding.local>")

# Where links in emails point (the React app).
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173").rstrip("/")
# Off for the demo so testers on phones aren't blocked; emails are still sent.
REQUIRE_EMAIL_VERIFICATION = env.bool("REQUIRE_EMAIL_VERIFICATION", default=False)

# Fernet keys for personal data at rest, newest first (MultiFernet allows rotation). Generate one with:
#   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DATA_ENCRYPTION_KEYS = env.list("DATA_ENCRYPTION_KEYS", default=[DEV_ENCRYPTION_KEY])
EVIDENCE_DIR = Path(env("EVIDENCE_DIR", default=str(REPO_ROOT / "data" / "evidence")))

# Check Share Code (checksharecode.co.uk): live share code and DVLA check code lookups.
# rtw_test_... = sandbox (test codes, never reaches gov.uk); rtw_live_... = real gov.uk checks.
CHECKSHARECODE_API_KEY = env("CHECKSHARECODE_API_KEY", default="")
CHECKSHARECODE_BASE_URL = env("CHECKSHARECODE_BASE_URL", default="https://api.checksharecode.co.uk")
# Recorded by gov.uk as the employer making each right to work check.
EMPLOYER_NAME = env("EMPLOYER_NAME", default="")

# Only "stub" exists: it always matches, and the decision gate sends those cases to a reviewer.
IDENTITY_PROVIDER = env("IDENTITY_PROVIDER", default="stub")

# Live checks cost money: limit attempts per application and across the service.
LIVE_CHECK_ATTEMPTS_PER_DAY = env.int("LIVE_CHECK_ATTEMPTS_PER_DAY", default=3)
LIVE_CHECK_GLOBAL_DAILY_LIMIT = env.int("LIVE_CHECK_GLOBAL_DAILY_LIMIT", default=20)
LIVE_CHECK_RETRY_DELAY_SECONDS = env.int("LIVE_CHECK_RETRY_DELAY_SECONDS", default=20)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {"httpx": {"level": "WARNING"}},
}
