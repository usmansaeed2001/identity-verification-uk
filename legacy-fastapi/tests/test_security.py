import json
import time
import uuid

import httpx
import pytest

from app import db
from app.main import create_app
from app.providers.mock_rtw import MockRtwProvider
from app.security import sign
from app.services.orchestrator import load_case
from tests.conftest import INTERNAL, HostApi, make_settings


async def test_requests_without_api_key_or_signature_are_rejected(client, host):
    assert (await client.get("/v1/verifications/00000000-0000-0000-0000-000000000000")).status_code == 401

    body = b"{}"
    headers = host.headers(body)
    headers["X-Signature"] = "sha256=" + "0" * 64
    assert (await client.post("/v1/verifications", content=body, headers=headers)).status_code == 401

    stale = str(int(time.time()) - 3600)
    headers = host.headers(body)
    headers.update(
        {"X-Timestamp": stale, "X-Signature": f"sha256={sign(host.settings.host_signing_secret, stale, body)}"}
    )
    assert (await client.post("/v1/verifications", content=body, headers=headers)).status_code == 401


async def test_live_mode_needs_a_configured_provider(host):
    response = await host.create(mode="live")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_not_configured"


async def test_scenario_must_fit_route(host):
    response = await host.create(route="british_irish", mock_scenario="rtw_expired")
    assert response.status_code == 422
    assert (await host.create(mock_scenario="nope")).status_code == 422


async def test_drivers_must_be_adults(host):
    response = await host.create(dob="2015-01-01")
    assert response.status_code == 422


async def test_provider_webhook_signature_and_replay(app, host, client, settings):
    case_id = (await host.create()).json()["id"]
    async with db.session_factory()() as session:
        case = await load_case(session, uuid.UUID(case_id))
        body, headers = MockRtwProvider(settings).build_completion(case)

    forged = dict(headers, **{"X-Mock-Signature": "sha256=" + "0" * 64})
    assert (await client.post("/webhooks/mock_rtw", content=body, headers=forged)).status_code == 401

    first = await client.post("/webhooks/mock_rtw", content=body, headers=headers)
    assert first.json() == {"status": "accepted"}
    replay = await client.post("/webhooks/mock_rtw", content=body, headers=headers)
    assert replay.json() == {"status": "duplicate"}
    assert (await client.post("/webhooks/unknown_vendor", content=body, headers=headers)).status_code == 404


PROD_SECRETS = dict(
    host_api_key="prod-key",
    host_signing_secret="prod-signing",
    webhook_signing_secret="prod-webhook",
    evidence_url_secret="prod-evidence",
    mock_provider_secret="prod-mock",
    data_encryption_key="M2Q2ZjRhYjE4Y2E0NDFiYjk5ZWFkMWYyMzM5YjBkNGM=",
)


def test_production_refuses_dev_secrets(tmp_path):
    with pytest.raises(ValueError, match="host_api_key"):
        make_settings(tmp_path, environment="production")


async def test_production_has_no_mock_mode_demo_or_mock_webhook(tmp_path):
    settings = make_settings(tmp_path, environment="production", **PROD_SECRETS)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with db._engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=INTERNAL) as client:
            host = HostApi(client, settings)
            response = await host.create(mode="mock")
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "forbidden"

            assert (await client.get("/demo")).status_code == 404
            assert (await client.get("/demo/admin")).status_code == 404
            assert (await client.post("/webhooks/mock_rtw", content=json.dumps({}).encode())).status_code == 404
