from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from providers.base import IdentityProvider
from providers.identity_stub import StubIdentityProvider


def identity_provider() -> IdentityProvider:
    if settings.IDENTITY_PROVIDER == "stub":
        return StubIdentityProvider()
    raise ImproperlyConfigured(f"Unknown IDENTITY_PROVIDER: {settings.IDENTITY_PROVIDER}")
