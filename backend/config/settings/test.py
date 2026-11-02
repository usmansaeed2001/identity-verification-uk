import tempfile
from pathlib import Path

from config.settings.base import *  # noqa: F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CELERY_TASK_ALWAYS_EAGER = True
EVIDENCE_DIR = Path(tempfile.mkdtemp(prefix="evidence-"))
STORAGES = {"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}

# Tests never use the developer's real key; each test sets the key it needs.
CHECKSHARECODE_API_KEY = "rtw_test_key"
CHECKSHARECODE_BASE_URL = "https://checksharecode.test"
EMPLOYER_NAME = "Test Haulage Ltd"
REQUIRE_EMAIL_VERIFICATION = False
LIVE_CHECK_RETRY_DELAY_SECONDS = 0
