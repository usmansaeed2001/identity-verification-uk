"""Real share code and DVLA check code flow, against a fake of the Check Share Code API."""

import re
import uuid

import pytest
from sqlalchemy import select

from app import db
from app.domain.models import Evidence, OutboundWebhook
from app.providers import checksharecode
from tests.conftest import drain, make_settings
from tests.fake_checksharecode import FakeCheckShareCode

LICENCE = "NOWAK803147T99AB"
CSC = dict(
    rtw_provider="checksharecode",
    licence_provider="checksharecode",
    checksharecode_api_key="rtw_test_sandboxkey",
    employer_name="Northway Haulage Ltd",
)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path, **CSC)


@pytest.fixture
def fake(monkeypatch):
    fake = FakeCheckShareCode()
    client = fake.client()
    monkeypatch.setattr(checksharecode, "get_http_client", lambda: client)
    return fake


async def start_case(host, **overrides):
    response = await host.create(mode="live", **overrides)
    assert response.status_code == 201, response.text
    return response.json()


async def submit(app, host, case_id, share_code="AA1AA1AA1", check_code="AAAA1234"):
    r = await host.request(
        "POST", f"/v1/verifications/{case_id}/share-code", {"share_code": share_code, "date_of_birth": "1987-03-14"}
    )
    assert r.status_code == 202, r.text
    r = await host.request(
        "POST",
        f"/v1/verifications/{case_id}/licence",
        {"licence_number": LICENCE, "dvla_consent": True, "check_code": check_code},
    )
    assert r.status_code == 200, r.text
    await drain(app)
    return await host.get(case_id)


async def webhooks(case_id):
    async with db.session_factory()() as session:
        rows = await session.execute(
            select(OutboundWebhook)
            .where(OutboundWebhook.case_id == uuid.UUID(case_id))
            .order_by(OutboundWebhook.created_at)
        )
        return rows.scalars().all()


def checks_of(case):
    return {c["type"]: c for c in case["checks"]}


async def test_accepted_share_code_and_clean_licence_go_to_photo_review(app, host, fake):
    created = await start_case(host)
    assert created["is_test"] is True  # sandbox key
    case = await submit(app, host, created["id"])

    assert case["status"] == "MANUAL_REVIEW"
    checks = checks_of(case)
    assert checks["right_to_work"]["status"] == "unclear"
    assert "Compare the Home Office photo" in checks["right_to_work"]["reasons"][0]
    assert checks["identity_document"]["status"] == "skipped"
    assert checks["liveness"]["status"] == "skipped"
    assert checks["name_dob_match"]["status"] == "pass"
    assert checks["dvla_licence"]["status"] == "pass"
    assert checks["driver_cpc"]["status"] == "unclear"
    assert case["rtw_expires_at"] == "2027-01-01"

    rtw_call, licence_call = fake.requests
    assert rtw_call["auth"] == "Bearer rtw_test_sandboxkey"
    assert rtw_call["body"] == {
        "share_code": "AA1AA1AA1",
        "date_of_birth": "1987-03-14",
        "company_name": "Northway Haulage Ltd",
    }
    assert licence_call["body"] == {"licence_number": LICENCE, "check_code": "AAAA1234"}

    async with db.session_factory()() as session:
        kinds = sorted((await session.execute(select(Evidence.kind))).scalars())
    assert kinds == ["dvla_summary", "home_office_photo", "rtw_profile"]

    hooks = await webhooks(created["id"])
    assert [h.event for h in hooks] == ["verification.requires_review"]
    assert hooks[0].payload["licence"]["categories"] == ["B", "C", "C1", "CE"]

    approved = await host.request(
        "POST",
        f"/v1/verifications/{created['id']}/review",
        {
            "decision": "approve",
            "note": "Video call: matches Home Office photo. DQC seen, valid.",
            "reviewed_by": "ops",
        },
    )
    assert approved.json()["status"] == "PASSED"


async def test_codes_are_cleared_after_use(app, host, fake):
    created = await start_case(host)
    await submit(app, host, created["id"])
    async with db._engine.connect() as conn:
        row = (
            await conn.exec_driver_sql(
                "SELECT rtw_share_code, rtw_share_code_dob, dvla_check_code FROM verification_cases"
            )
        ).one()
    assert row == (None, None, None)


async def test_rejected_share_code_fails_without_a_licence_check(app, host, fake):
    created = await start_case(host)
    case = await submit(app, host, created["id"], share_code="BB2BB2BB2")
    assert case["status"] == "FAILED"
    assert checks_of(case)["dvla_licence"]["status"] == "skipped"
    assert [r["path"] for r in fake.requests] == ["/v1/check/right-to-work"]


async def test_unknown_share_code_asks_the_driver_again(app, host, fake):
    created = await start_case(host)
    case = await submit(app, host, created["id"], share_code="CC3CC3CC3")
    assert case["status"] == "AWAITING_DRIVER"
    assert case["driver_action_required"][0]["check"] == "right_to_work"
    assert "no record" in case["driver_action_required"][0]["message"]
    hooks = await webhooks(created["id"])
    assert hooks[-1].event == "verification.driver_action_required"
    assert hooks[-1].payload["driver_action_required"][0]["code"] == "NOT_FOUND"

    retry = await host.request(
        "POST",
        f"/v1/verifications/{created['id']}/share-code",
        {"share_code": "AA1AA1AA1", "date_of_birth": "1987-03-14"},
    )
    assert retry.status_code == 202
    await drain(app)
    case = await host.get(created["id"])
    assert case["status"] == "MANUAL_REVIEW"
    assert case["driver_action_required"] == []


async def test_refused_check_code_asks_for_a_new_one(app, host, fake):
    created = await start_case(host)
    case = await submit(app, host, created["id"], check_code="DDDD1234")
    assert case["status"] == "IN_PROGRESS"
    assert case["driver_action_required"][0]["check"] == "dvla_licence"

    retry = await host.request(
        "POST",
        f"/v1/verifications/{created['id']}/licence",
        {"licence_number": LICENCE, "dvla_consent": True, "check_code": "AAAA5678"},
    )
    assert retry.status_code == 200, retry.text
    await drain(app)
    case = await host.get(created["id"])
    assert case["status"] == "MANUAL_REVIEW"
    assert checks_of(case)["dvla_licence"]["status"] == "pass"


async def test_dvla_error_after_code_was_sent_asks_for_new_code_instead_of_retrying(app, host, fake):
    created = await start_case(host)
    case = await submit(app, host, created["id"], check_code="EEEE1234")
    assert "used up" in case["driver_action_required"][0]["message"]
    assert len([r for r in fake.requests if r["path"].endswith("driving-licence")]) == 1


async def test_busy_is_retried(app, host, fake):
    import httpx

    fake.forced.append(httpx.Response(503, json={"error": {"code": "BUSY", "message": "busy"}}))
    created = await start_case(host)
    case = await submit(app, host, created["id"])
    assert case["status"] == "MANUAL_REVIEW"
    assert [r["path"] for r in fake.requests].count("/v1/check/right-to-work") == 2


async def test_no_hgv_entitlement_fails(app, host, fake):
    created = await start_case(host)
    case = await submit(app, host, created["id"], check_code="BBBB1234")
    assert case["status"] == "FAILED"
    assert "C or C+E" in checks_of(case)["dvla_licence"]["reasons"][0]


async def test_points_are_reported_but_do_not_fail(app, host, fake):
    created = await start_case(host)
    case = await submit(app, host, created["id"], check_code="CCCC1234")
    assert checks_of(case)["dvla_licence"]["status"] == "pass"


async def test_live_mode_rules(app, host, fake):
    british = await host.create(mode="live", route="british_irish")
    assert british.status_code == 422
    assert "identity provider" in british.json()["error"]["message"]

    created = await start_case(host)
    no_code = await host.request(
        "POST", f"/v1/verifications/{created['id']}/licence", {"licence_number": LICENCE, "dvla_consent": True}
    )
    assert no_code.status_code == 422
    bad_code = await host.request(
        "POST",
        f"/v1/verifications/{created['id']}/licence",
        {"licence_number": LICENCE, "dvla_consent": True, "check_code": "short"},
    )
    assert bad_code.status_code == 422

    mock_case = (await host.create(mode="mock")).json()
    on_mock = await host.request(
        "POST",
        f"/v1/verifications/{mock_case['id']}/share-code",
        {"share_code": "AA1AA1AA1", "date_of_birth": "1987-03-14"},
    )
    assert on_mock.status_code == 409


@pytest.mark.parametrize(
    "payload, path",
    [
        ({"share_code": "AA1 AA1 AA1", "date_of_birth": "1990-01-01", "company_name": "X"}, "/v1/check/right-to-work"),
        ({"licence_number": LICENCE, "check_code": "AaAa1234"}, "/v1/check/driving-licence"),
    ],
)
async def test_live_key_never_sends_sandbox_test_codes(tmp_path, fake, payload, path):
    live = make_settings(tmp_path, **{**CSC, "checksharecode_api_key": "rtw_live_x"})
    with pytest.raises(checksharecode.DriverInputError, match="sandbox test code"):
        await checksharecode.CheckShareCodeClient(live).post(path, payload)
    assert fake.requests == []  # refused before any request left the process


async def test_sandbox_key_sends_test_codes(tmp_path, fake):
    data = await checksharecode.CheckShareCodeClient(make_settings(tmp_path, **CSC)).post(
        "/v1/check/right-to-work", {"share_code": "AA1AA1AA1", "date_of_birth": "1990-01-01", "company_name": "X"}
    )
    assert data["outcome"] == "ACCEPTED"


def test_live_key_cases_are_not_test_data(tmp_path):
    assert (
        make_settings(tmp_path, **{**CSC, "checksharecode_api_key": "rtw_live_x"}).live_providers_are_sandbox is False
    )
    with pytest.raises(ValueError, match="checksharecode_api_key"):
        make_settings(tmp_path, **{**CSC, "checksharecode_api_key": None})


async def test_demo_journey_with_real_checks(app, client, fake):
    start = await client.post(
        "/demo/start",
        data={"first_name": "Tomasz", "last_name": "Nowak", "dob": "1987-03-14", "route": "share_code", "mode": "live"},
    )
    assert start.status_code == 303, start.text
    case_id = start.headers["location"].rsplit("/", 1)[-1]
    base = f"/demo/driver/{case_id}"

    consent = await client.get(f"{base}/consent")
    assert "Step 1 of 3" in consent.text and "Sandbox" in consent.text
    assert (await client.post(f"{base}/consent", data={"agree": "yes"})).headers["location"] == f"{base}/share-code"
    assert (await client.get(f"{base}/document")).status_code == 404  # identity deferred

    page = await client.post(f"{base}/share-code", data={"share_code": "CC3 CC3 CC3", "dob": "1987-03-14"})
    assert page.headers["location"] == f"{base}/licence"
    licence_page = await client.get(f"{base}/licence")
    assert "DVLA check code" in licence_page.text and "AAAA1234" in licence_page.text
    done = await client.post(
        f"{base}/licence", data={"licence_number": LICENCE, "check_code": "Aa Aa 12 34", "dvla_consent": "yes"}
    )
    assert done.headers["location"] == f"{base}/checking"
    await drain(app)

    status = await client.get(f"{base}/status")
    assert "Enter a new share code" in status.text

    retried = await client.post(f"{base}/share-code", data={"share_code": "AA1 AA1 AA1", "dob": "1987-03-14"})
    assert retried.headers["location"] == f"{base}/checking"
    await drain(app)

    admin = await client.get(f"/demo/admin/cases/{case_id}")
    assert "Review this case" in admin.text
    assert "Photo held by the Home Office" in admin.text
    assert "DVLA: Current full licence" in admin.text
    photo = re.search(r'class="ho-photo" src="([^"]+)"', admin.text).group(1)
    redirect = await client.get(photo)
    image = await client.get(redirect.headers["location"])
    assert image.headers["content-type"] == "image/jpeg"
