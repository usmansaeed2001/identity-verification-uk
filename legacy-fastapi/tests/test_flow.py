"""End-to-end through the API with the mock providers, including real webhook delivery."""

import uuid

import pytest
from sqlalchemy import select

from app import db
from app.domain.models import AuditEvent, OutboundWebhook
from app.workers.queue import get_queue
from tests.conftest import drain

LICENCE = "NOWAK803147T99AB"


async def run_case(app, host, **create):
    created = await host.create(**create)
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    licence = await host.request(
        "POST", f"/v1/verifications/{case_id}/licence", {"licence_number": LICENCE, "dvla_consent": True}
    )
    assert licence.status_code == 200, licence.text
    # The driver finishes the vendor's hosted flow; the mock vendor reports back by webhook.
    await get_queue().enqueue("deliver_mock_rtw_webhook", case_id=case_id)
    await drain(app)
    return case_id, await host.get(case_id)


async def webhooks_for(case_id):
    async with db.session_factory()() as session:
        rows = await session.execute(select(OutboundWebhook).where(OutboundWebhook.case_id == case_id))
        return rows.scalars().all()


@pytest.mark.parametrize(
    "scenario, route, expected",
    [
        ("all_pass", "share_code", "PASSED"),
        ("all_pass", "british_irish", "PASSED"),
        ("rtw_expired", "share_code", "FAILED"),
        ("face_mismatch", "share_code", "MANUAL_REVIEW"),
        ("name_mismatch", "british_irish", "MANUAL_REVIEW"),
        ("no_hgv_entitlement", "share_code", "FAILED"),
        ("cpc_expired", "british_irish", "FAILED"),
        ("dvla_timeout", "share_code", "MANUAL_REVIEW"),
    ],
)
async def test_each_scenario_reaches_its_outcome(app, host, scenario, route, expected):
    case_id, case = await run_case(app, host, mock_scenario=scenario, route=route)
    assert case["status"] == expected
    assert case["is_test"] is True
    assert all(c["status"] != "pending" for c in case["checks"])

    hooks = await webhooks_for(uuid.UUID(case_id))
    assert len(hooks) == 1
    hook = hooks[0]
    assert hook.event == ("verification.requires_review" if expected == "MANUAL_REVIEW" else "verification.completed")
    assert hook.delivered_at is not None and hook.last_status_code == 200  # demo receiver verified our signature
    assert hook.payload["status"] == expected
    assert hook.payload["is_test"] is True


async def test_passed_share_code_case_records_expiry_and_licence(app, host):
    _, case = await run_case(app, host)
    assert case["rtw_expires_at"] is not None
    checks = {c["type"]: c for c in case["checks"]}
    assert checks["dvla_licence"]["status"] == "pass"
    assert checks["name_dob_match"]["status"] == "pass"


async def test_rtw_failure_skips_remaining_checks_and_dvla(app, host):
    _, case = await run_case(app, host, mock_scenario="rtw_expired")
    checks = {c["type"]: c for c in case["checks"]}
    assert "ended on" in checks["right_to_work"]["reasons"][0]
    assert checks["dvla_licence"]["status"] == "skipped"


async def test_dvla_timeout_is_retried_before_review(app, host):
    case_id, _ = await run_case(app, host, mock_scenario="dvla_timeout")
    async with db.session_factory()() as session:
        actions = (
            (await session.execute(select(AuditEvent.action).where(AuditEvent.case_id == uuid.UUID(case_id))))
            .scalars()
            .all()
        )
    assert actions.count("dvla.lookup_retry") == 2
    assert "dvla.lookup_failed" in actions


async def test_manual_review_approval_completes_the_case(app, host):
    case_id, case = await run_case(app, host, mock_scenario="face_mismatch")
    assert case["status"] == "MANUAL_REVIEW"
    reviewed = await host.request(
        "POST",
        f"/v1/verifications/{case_id}/review",
        {"decision": "approve", "note": "Compared photos by eye; same person.", "reviewed_by": "ops@haulier"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "PASSED"
    await drain(app)
    hooks = await webhooks_for(uuid.UUID(case_id))
    assert [h.event for h in hooks] == ["verification.requires_review", "verification.completed"]
    assert hooks[1].payload["review"]["decision"] == "approve"

    again = await host.request(
        "POST",
        f"/v1/verifications/{case_id}/review",
        {"decision": "reject", "note": "changed my mind", "reviewed_by": "ops"},
    )
    assert again.status_code == 409


async def test_evidence_links_are_signed_and_expire(app, host, client, settings):
    case_id, _ = await run_case(app, host)
    listing = await host.request("GET", f"/v1/verifications/{case_id}/evidence")
    item = listing.json()["items"][0]
    assert item["kind"] == "rtw_profile"
    path = item["url"].removeprefix(settings.public_base_url)
    pdf = await client.get(path)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF") and b"SIMULATED" in pdf.content

    tampered = await client.get(path.replace("signature=", "signature=0"))
    assert tampered.status_code == 401
    expired = await client.get(f"/v1/evidence/{item['id']}?expires=1&signature=abc")
    assert expired.status_code == 401


async def test_personal_data_is_encrypted_at_rest(app, host):
    await run_case(app, host)
    async with db._engine.connect() as conn:
        raw = (await conn.exec_driver_sql("SELECT first_name, licence_number FROM drivers")).one()
    assert "Tomasz" not in raw[0] and "NOWAK" not in raw[1]


async def test_licence_cannot_be_resubmitted_once_checked(app, host):
    case_id, _ = await run_case(app, host)
    again = await host.request(
        "POST", f"/v1/verifications/{case_id}/licence", {"licence_number": LICENCE, "dvla_consent": True}
    )
    assert again.status_code == 409


async def test_licence_requires_consent(app, host):
    created = (await host.create()).json()
    response = await host.request(
        "POST", f"/v1/verifications/{created['id']}/licence", {"licence_number": LICENCE, "dvla_consent": False}
    )
    assert response.status_code == 422
    assert response.json()["error"]["fields"][0]["field"] == "dvla_consent"
