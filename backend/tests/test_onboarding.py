"""The driver journey end to end, against the fake Check Share Code API (Celery runs eagerly)."""

import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from django.core import mail
from django.db import connection

from onboarding.models import Application
from onboarding.services import BRITISH_IRISH_REASON
from providers import checksharecode
from tests.conftest import LICENCE, fill_identity, photo, run_checks

pytestmark = pytest.mark.django_db(transaction=True)


def checks_of(detail: dict) -> dict:
    return {c["type"]: c for c in detail["checks"]}


def submit(client) -> dict:
    r = client.post("/api/driver/submit")
    assert r.status_code == 200, r.json()
    return r.json()


def test_share_code_journey_ends_in_review_and_can_be_approved(driver, reviewer, fake):
    state = fill_identity(driver)
    assert state["next_step"] == "right_to_work"
    state = run_checks(driver)
    assert state["right_to_work"]["state"] == "done"
    assert state["licence"]["state"] == "done"
    assert state["can_submit"] is True

    rtw_call, licence_call = fake.requests
    assert rtw_call["auth"] == "Bearer rtw_test_key"
    assert rtw_call["body"] == {
        "share_code": "AA1AA1AA1",
        "date_of_birth": "1987-03-14",
        "company_name": "Test Haulage Ltd",
    }
    assert licence_call["body"] == {"licence_number": LICENCE, "check_code": "AAAA1234"}

    mail.outbox.clear()
    state = submit(driver)
    assert state["status"] == "MANUAL_REVIEW"
    assert "right_to_work" not in str(state.get("checks", ""))  # the driver never sees check results
    assert mail.outbox[0].subject == "We've got your driver application"

    detail = reviewer.get(f"/api/staff/applications/{state['id']}").json()
    assert detail["is_test"] is True  # sandbox key
    checks = checks_of(detail)
    assert checks["right_to_work"]["status"] == "unclear"
    assert "Compare the Home Office photo" in checks["right_to_work"]["reasons"][0]
    for simulated in ("identity_document", "liveness", "face_match"):
        assert checks[simulated]["status"] == "pass"
        assert checks[simulated]["simulated"] is True
    assert checks["name_dob_match"]["status"] == "pass"
    assert checks["dvla_licence"]["status"] == "pass"
    assert checks["dvla_licence"]["details"]["categories"] == ["B", "C", "C1", "CE"]
    assert checks["driver_cpc"]["status"] == "unclear"
    assert "didn't upload a DQC card" in checks["driver_cpc"]["reasons"][-1]
    assert detail["rtw_expires_at"] == "2027-01-01"
    assert detail["licence_number"] == LICENCE
    kinds = sorted(e["kind"] for e in detail["evidence"])
    assert kinds == [
        "dvla_summary_pdf",
        "home_office_photo",
        "id_front",
        "rtw_profile_pdf",
        "selfie",
        "selfie",
        "selfie",
    ]

    selfie = next(e for e in detail["evidence"] if e["kind"] == "selfie")
    image = reviewer.get(selfie["url"])
    assert image.status_code == 200
    assert image["Content-Type"] == "image/jpeg"
    assert image["Cache-Control"] == "no-store"
    assert b"Exif" not in image.content[:200]

    approved = reviewer.post(
        f"/api/staff/applications/{state['id']}/review",
        {"decision": "approve", "note": "Video call: matches the Home Office photo. DQC seen."},
        format="json",
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "PASSED"
    assert "evidence_viewed" in [a["action"] for a in approved.json()["audit"]]
    assert mail.outbox[-1].subject == "You're approved"
    assert driver.get("/api/driver/application").json()["status"] == "PASSED"


def test_codes_are_encrypted_and_cleared_after_use(driver):
    fill_identity(driver)
    run_checks(driver)
    with connection.cursor() as cursor:
        cursor.execute("SELECT share_code, share_code_dob, dvla_check_code, first_name FROM onboarding_application")
        share_code, share_code_dob, check_code, first_name = cursor.fetchone()
    assert (share_code, share_code_dob, check_code) == (None, None, None)
    assert first_name and "Tomasz" not in first_name  # stored encrypted


def test_paid_checks_wait_until_identity_is_done(driver, fake):
    driver.put(
        "/api/driver/profile",
        {"first_name": "T", "last_name": "N", "dob": "1987-03-14", "phone": "07700900123", "route": "share_code"},
        format="json",
    )
    r = driver.post("/api/driver/right-to-work", {"share_code": "AA1AA1AA1"}, format="json")
    assert r.status_code == 409
    assert "Consent" in r.json()["detail"]
    assert fake.requests == []


def test_unknown_share_code_asks_for_it_again(driver):
    fill_identity(driver)
    state = run_checks(driver, share_code="CC3CC3CC3")
    assert state["right_to_work"]["state"] == "needs_new_code"
    assert "no record" in state["right_to_work"]["message"]
    assert state["can_submit"] is False
    assert driver.post("/api/driver/submit").status_code == 409

    r = driver.post("/api/driver/right-to-work", {"share_code": "AA1 AA1 AA1"}, format="json")
    assert r.json()["right_to_work"]["state"] == "done"


def test_refused_check_code_asks_for_a_new_one(driver):
    fill_identity(driver)
    state = run_checks(driver, check_code="DDDD1234")
    assert state["licence"]["state"] == "needs_new_code"
    r = driver.post("/api/driver/licence", {"licence_number": LICENCE, "check_code": "AAAA5678"}, format="json")
    assert r.json()["licence"]["state"] == "done"


def test_dvla_error_after_code_was_sent_asks_for_new_code_instead_of_retrying(driver, fake):
    fill_identity(driver)
    state = run_checks(driver, share_code=None, check_code="EEEE1234")
    assert "used up" in state["licence"]["message"]
    assert len([r for r in fake.requests if r["path"].endswith("driving-licence")]) == 1


def test_busy_is_retried(driver, fake):
    fake.forced.append(httpx.Response(503, json={"error": {"code": "BUSY", "message": "busy"}}))
    fill_identity(driver)
    state = run_checks(driver)
    assert state["right_to_work"]["state"] == "done"
    assert [r["path"] for r in fake.requests].count("/v1/check/right-to-work") == 2


def test_provider_outage_goes_to_reviewer_with_the_code(driver, reviewer, fake):
    for _ in range(3):
        fake.forced.append(httpx.Response(503, json={"error": {"code": "BUSY", "message": "busy"}}))
    fill_identity(driver)
    state = run_checks(driver)
    assert state["right_to_work"]["state"] == "done"
    detail = reviewer.get(f"/api/staff/applications/{submit(driver)['id']}").json()
    rtw = checks_of(detail)["right_to_work"]
    assert rtw["status"] == "unclear"
    assert rtw["details"]["share_code"] == "AA1AA1AA1"  # so the reviewer can check gov.uk themselves


def test_home_office_rejection_fails(driver):
    fill_identity(driver)
    run_checks(driver, share_code="BB2BB2BB2")
    assert submit(driver)["status"] == "FAILED"


def test_no_hgv_entitlement_fails(driver, reviewer):
    fill_identity(driver)
    run_checks(driver, check_code="BBBB1234")
    state = submit(driver)
    assert state["status"] == "FAILED"
    detail = reviewer.get(f"/api/staff/applications/{state['id']}").json()
    assert "C or C+E" in checks_of(detail)["dvla_licence"]["reasons"][0]


def test_name_that_doesnt_match_the_home_office_fails(driver):
    fill_identity(driver, first_name="Adam")
    run_checks(driver)
    assert submit(driver)["status"] == "FAILED"


def test_british_irish_route_skips_share_code_and_needs_a_person(driver, reviewer, fake):
    state = fill_identity(driver, route="british_irish")
    assert [s["key"] for s in state["steps"]] == ["profile", "consent", "document", "selfie", "licence"]
    assert driver.post("/api/driver/right-to-work", {"share_code": "AA1AA1AA1"}, format="json").status_code == 409
    run_checks(driver, share_code=None)
    state = submit(driver)
    assert state["status"] == "MANUAL_REVIEW"
    detail = reviewer.get(f"/api/staff/applications/{state['id']}").json()
    assert checks_of(detail)["right_to_work"]["reasons"] == [BRITISH_IRISH_REASON]
    assert [r["path"] for r in fake.requests] == ["/v1/check/driving-licence"]


def test_paid_check_attempts_are_limited(driver, fake, settings):
    settings.LIVE_CHECK_ATTEMPTS_PER_DAY = 2
    fill_identity(driver)
    for _ in range(2):
        r = driver.post("/api/driver/right-to-work", {"share_code": "CC3CC3CC3"}, format="json")
        assert r.status_code == 200
    r = driver.post("/api/driver/right-to-work", {"share_code": "AA1AA1AA1"}, format="json")
    assert r.status_code == 429
    assert len(fake.requests) == 2


def test_live_checks_need_a_key(driver, settings):
    settings.CHECKSHARECODE_API_KEY = ""
    fill_identity(driver)
    r = driver.post("/api/driver/right-to-work", {"share_code": "AA1AA1AA1"}, format="json")
    assert r.status_code == 503


@pytest.mark.parametrize(
    "payload, path",
    [
        ({"share_code": "AA1 AA1 AA1", "date_of_birth": "1990-01-01", "company_name": "X"}, "/v1/check/right-to-work"),
        ({"licence_number": LICENCE, "check_code": "AaAa1234"}, "/v1/check/driving-licence"),
    ],
)
def test_live_key_never_sends_sandbox_test_codes(fake, settings, payload, path):
    settings.CHECKSHARECODE_API_KEY = "rtw_live_x"
    with pytest.raises(checksharecode.DriverInputError, match="sandbox test code"):
        checksharecode.CheckShareCodeClient().post(path, payload)
    assert fake.requests == []  # refused before any request left the process


def test_live_key_requires_real_share_codes(driver, settings):
    settings.CHECKSHARECODE_API_KEY = "rtw_live_x"
    fill_identity(driver)
    r = driver.post("/api/driver/right-to-work", {"share_code": "AA1AA1AA1"}, format="json")
    assert r.status_code == 400
    assert "start with W" in r.json()["detail"]


def test_reviewer_can_send_steps_back(driver, reviewer):
    fill_identity(driver)
    run_checks(driver)
    app_id = submit(driver)["id"]

    r = reviewer.post(
        f"/api/staff/applications/{app_id}/request-action",
        {"steps": ["document", "licence"], "message": "The ID photo is blurry. Please retake it."},
        format="json",
    )
    assert r.status_code == 200
    state = driver.get("/api/driver/application").json()
    assert state["status"] == "ACTION_REQUIRED"
    assert state["action"]["message"] == "The ID photo is blurry. Please retake it."
    editable = {s["key"]: s["editable"] for s in state["steps"]}
    assert editable == {
        "profile": False,
        "consent": False,
        "document": True,
        "selfie": False,
        "right_to_work": False,
        "licence": True,
    }
    assert driver.post("/api/driver/consent", {"data_consent": True, "dvla_consent": True}).status_code == 409
    assert driver.post("/api/driver/submit").status_code == 409

    r = driver.post(
        "/api/driver/identity/document",
        {"document_type": "uk_licence", "front": photo(), "back": photo("back.jpg")},
        format="multipart",
    )
    assert r.status_code == 200, r.json()
    run_checks(driver, share_code=None, check_code="AAAA9999")
    assert submit(driver)["status"] == "MANUAL_REVIEW"
    kinds = [e["kind"] for e in reviewer.get(f"/api/staff/applications/{app_id}").json()["evidence"]]
    assert kinds.count("id_front") == 1 and kinds.count("id_back") == 1


def test_dqc_card_is_noted_for_the_reviewer(driver, reviewer):
    fill_identity(driver)
    assert driver.post("/api/driver/licence/dqc", {"photo": photo()}, format="multipart").status_code == 200
    run_checks(driver)
    detail = reviewer.get(f"/api/staff/applications/{submit(driver)['id']}").json()
    assert "uploaded a DQC card" in checks_of(detail)["driver_cpc"]["reasons"][-1]


def test_uploads_must_be_photos(driver):
    fill_identity(driver)
    from django.core.files.uploadedfile import SimpleUploadedFile

    bogus = SimpleUploadedFile("id.jpg", b"not an image", content_type="image/jpeg")
    r = driver.post("/api/driver/identity/document", {"document_type": "passport", "front": bogus}, format="multipart")
    assert r.status_code == 400


def test_face_scan_needs_three_frames(driver):
    fill_identity(driver)
    r = driver.post("/api/driver/identity/selfie", {"frames": [photo()]}, format="multipart")
    assert r.status_code == 400


def test_permissions(driver, reviewer):
    fill_identity(driver)
    app_id = Application.objects.get().id
    assert driver.get("/api/staff/applications").status_code == 403
    assert driver.get(f"/api/staff/applications/{app_id}").status_code == 403
    assert reviewer.get("/api/driver/application").status_code == 403
    from rest_framework.test import APIClient

    anonymous = APIClient()
    assert anonymous.get("/api/driver/application").status_code == 403
    assert anonymous.get("/api/staff/applications").status_code == 403


def test_reviewer_list_search_and_counts(driver, reviewer):
    fill_identity(driver)
    r = reviewer.get("/api/staff/applications", {"q": "tomasz"}).json()
    assert [row["email"] for row in r["results"]] == ["tomasz@example.com"]
    assert r["counts"] == {"DRAFT": 1}
    assert reviewer.get("/api/staff/applications", {"status": "PASSED"}).json()["results"] == []


def test_production_refuses_dev_secrets():
    backend = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings.prod"],
        cwd=backend,
        capture_output=True,
        text=True,
        env={"PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")},
    )
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr and "DATA_ENCRYPTION_KEYS" in result.stderr
