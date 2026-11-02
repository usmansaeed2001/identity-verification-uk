from app.config import Settings
from app.domain.models import VerificationCase
from app.errors import ProviderNotConfigured
from app.providers.base import LicenceProvider, RtwProvider, ShareCodeProvider
from app.providers.checksharecode import CheckShareCodeLicenceProvider, CheckShareCodeRtwProvider
from app.providers.mock_dvla import MockDvlaProvider
from app.providers.mock_rtw import MockRtwProvider

NOT_CONFIGURED = "No live verification provider is configured yet."


def provider_names(mock: bool, settings: Settings) -> tuple[str, str]:
    """The (RTW, licence) provider names a new case will use."""
    if mock:
        return MockRtwProvider.name, MockDvlaProvider.name
    if settings.rtw_provider == "checksharecode" and settings.licence_provider == "checksharecode":
        return CheckShareCodeRtwProvider.name, CheckShareCodeLicenceProvider.name
    raise ProviderNotConfigured(NOT_CONFIGURED)


def rtw_for_case(case: VerificationCase, settings: Settings) -> RtwProvider | ShareCodeProvider:
    if case.rtw_provider == MockRtwProvider.name:
        return MockRtwProvider(settings)
    if case.rtw_provider == CheckShareCodeRtwProvider.name:
        return CheckShareCodeRtwProvider(settings)
    raise ProviderNotConfigured(NOT_CONFIGURED)


def licence_for_case(case: VerificationCase, settings: Settings) -> LicenceProvider:
    if case.licence_provider == MockDvlaProvider.name:
        return MockDvlaProvider(settings)
    if case.licence_provider == CheckShareCodeLicenceProvider.name:
        return CheckShareCodeLicenceProvider(settings)
    raise ProviderNotConfigured(NOT_CONFIGURED)


def collects_share_code(case: VerificationCase) -> bool:
    """True when we take the share code ourselves instead of a vendor's hosted page."""
    return case.rtw_provider == CheckShareCodeRtwProvider.name


def rtw_by_webhook_name(name: str, settings: Settings) -> RtwProvider | None:
    """Resolve /webhooks/{name}. The mock vendor's endpoint doesn't exist in production."""
    if name == MockRtwProvider.name and not settings.is_production:
        return MockRtwProvider(settings)
    return None
