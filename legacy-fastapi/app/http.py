"""Shared outbound HTTP client.

Calls to our own internal_base_url (mock vendor webhooks, the demo host
receiver) go straight into the ASGI app when we have it, so they work behind
any port or tunnel. Everything else goes over the network.
"""

import httpx

_client: httpx.AsyncClient | None = None


def init_http_client(internal_base_url: str, app=None) -> httpx.AsyncClient:
    global _client
    mounts = {internal_base_url.rstrip("/"): httpx.ASGITransport(app=app)} if app is not None else None
    _client = httpx.AsyncClient(timeout=10.0, mounts=mounts)
    return _client


def get_http_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("HTTP client is not initialised")
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None
