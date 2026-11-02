import base64
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Fernet key for local development only. Production refuses to start with it.
DEV_ENCRYPTION_KEY = base64.urlsafe_b64encode(b"dev-only-key-do-not-use-in-prod!").decode()

DEV_SECRETS = {
    "host_api_key": "dev-api-key",
    "host_signing_secret": "dev-host-signing-secret",
    "webhook_signing_secret": "dev-webhook-signing-secret",
    "evidence_url_secret": "dev-evidence-url-secret",
    "mock_provider_secret": "dev-mock-provider-secret",
    "data_encryption_key": DEV_ENCRYPTION_KEY,
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    environment: Literal["development", "test", "staging", "production"] = "development"

    database_url: str = "sqlite+aiosqlite:///./data/dev.db"
    job_backend: Literal["inline", "arq"] = "inline"
    redis_url: str = "redis://localhost:6379/0"

    # public_base_url is what drivers and the host see; internal_base_url is how
    # the service reaches itself (mock vendor webhooks, demo host receiver).
    public_base_url: str = "http://localhost:8000"
    internal_base_url: str = "http://localhost:8000"
    default_callback_url: str | None = None

    host_api_key: str = DEV_SECRETS["host_api_key"]
    host_signing_secret: str = DEV_SECRETS["host_signing_secret"]
    webhook_signing_secret: str = DEV_SECRETS["webhook_signing_secret"]
    evidence_url_secret: str = DEV_SECRETS["evidence_url_secret"]
    mock_provider_secret: str = DEV_SECRETS["mock_provider_secret"]
    data_encryption_key: str = DEV_SECRETS["data_encryption_key"]

    evidence_backend: Literal["local", "s3"] = "local"
    evidence_dir: str = "./data/evidence"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "evidence"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    # Live providers: "checksharecode" for both, or None (mock mode only).
    rtw_provider: Literal["checksharecode"] | None = None
    licence_provider: Literal["checksharecode"] | None = None
    checksharecode_api_key: str | None = None  # rtw_test_... (sandbox) or rtw_live_...
    checksharecode_base_url: str = "https://api.checksharecode.co.uk"
    # Recorded by gov.uk as the employer who made each right to work check.
    employer_name: str | None = None

    mock_delay_min_seconds: float = 1.0
    mock_delay_max_seconds: float = 3.0

    rtw_expiry_notice_days: int = 28
    evidence_url_ttl_seconds: int = 300
    request_max_skew_seconds: int = 300
    test_case_retention_hours: int = 24
    webhook_max_attempts: int = 5

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def demo_enabled(self) -> bool:
        return not self.is_production

    @property
    def live_providers_configured(self) -> bool:
        return bool(self.rtw_provider and self.licence_provider)

    @property
    def live_providers_are_sandbox(self) -> bool:
        """Sandbox keys never reach gov.uk, so cases made with them are marked as test data."""
        return bool(self.checksharecode_api_key and self.checksharecode_api_key.startswith("rtw_test_"))

    @model_validator(mode="after")
    def _checksharecode_settings(self) -> "Settings":
        if "checksharecode" in (self.rtw_provider, self.licence_provider):
            missing = [n for n in ("checksharecode_api_key", "employer_name") if not getattr(self, n)]
            if missing:
                raise ValueError(f"Check Share Code needs these settings: {', '.join(missing)}")
        return self

    @model_validator(mode="after")
    def _no_dev_secrets_in_production(self) -> "Settings":
        if self.is_production:
            insecure = [name for name, value in DEV_SECRETS.items() if getattr(self, name) == value]
            if insecure:
                raise ValueError(f"Set real values for these settings in production: {', '.join(insecure)}")
        return self


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(settings: Settings) -> None:
    global _settings
    _settings = settings
