import hmac

from fastapi import Request

from app.config import Settings
from app.errors import Unauthorized
from app.security import verify_signature


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


async def require_host(request: Request) -> None:
    """The host sends X-API-Key plus an HMAC of "<X-Timestamp>.<body>" in X-Signature."""
    settings: Settings = request.app.state.settings
    api_key = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(api_key.encode(), settings.host_api_key.encode()):
        raise Unauthorized("Missing or invalid API key.")
    body = await request.body()
    if not verify_signature(
        settings.host_signing_secret,
        request.headers.get("X-Timestamp"),
        body,
        request.headers.get("X-Signature"),
        settings.request_max_skew_seconds,
    ):
        raise Unauthorized("Missing, invalid or expired request signature.")
