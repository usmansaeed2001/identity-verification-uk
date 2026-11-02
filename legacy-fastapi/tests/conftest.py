import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app import db
from app.config import Settings
from app.main import create_app
from app.security import sign

INTERNAL = "http://internal.test"
DEMO_CALLBACK = f"{INTERNAL}/demo/host-webhook"


def make_settings(tmp_path, **overrides: Any) -> Settings:
    values: dict[str, Any] = dict(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        internal_base_url=INTERNAL,
        public_base_url="http://public.test",
        evidence_dir=str(tmp_path / "evidence"),
        mock_delay_min_seconds=0,
        mock_delay_max_seconds=0,
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
async def app(settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with db._engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
        yield app


@pytest.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=INTERNAL) as client:
        yield client


class HostApi:
    """Signs requests the way the host platform must."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    def headers(self, body: bytes) -> dict[str, str]:
        timestamp = str(int(time.time()))
        return {
            "Content-Type": "application/json",
            "X-API-Key": self.settings.host_api_key,
            "X-Timestamp": timestamp,
            "X-Signature": f"sha256={sign(self.settings.host_signing_secret, timestamp, body)}",
        }

    async def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> httpx.Response:
        body = json.dumps(payload).encode() if payload is not None else b""
        return await self.client.request(method, path, content=body, headers=self.headers(body))

    async def create(self, **overrides: Any) -> httpx.Response:
        payload = {
            "external_driver_id": "drv_48213",
            "first_name": "Tomasz",
            "last_name": "Nowak",
            "dob": "1987-03-14",
            "route": "share_code",
            "mode": "mock",
            "callback_url": DEMO_CALLBACK,
        }
        payload.update(overrides)
        return await self.request("POST", "/v1/verifications", payload)

    async def get(self, case_id: str) -> dict[str, Any]:
        response = await self.request("GET", f"/v1/verifications/{case_id}")
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def host(client, settings) -> HostApi:
    return HostApi(client, settings)


async def drain(app) -> None:
    await app.state.queue.drain()
