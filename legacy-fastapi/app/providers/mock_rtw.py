"""Simulated right-to-work vendor.

It behaves like a hosted vendor: it hands out a driver link (our /demo pages
play the vendor's screens), then reports results through a signed webhook to
/webhooks/mock_rtw, so the real webhook pipeline runs end to end.
"""

import base64
import json
import random
import uuid
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from app.config import Settings
from app.domain.enums import CheckStatus, EvidenceKind, Route
from app.domain.models import VerificationCase
from app.providers.base import CheckOutcome, EvidenceFile, Person, RtwResult, RtwSession
from app.providers.pdf import simple_pdf
from app.security import signed_headers, verify_signature

SIGNATURE_PREFIX = "X-Mock"
MIDDLE_NAME = "Lee"
FACE_THRESHOLD = 0.80


class MockRtwProvider:
    name = "mock_rtw"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def create_session(self, case: VerificationCase) -> RtwSession:
        return RtwSession(
            session_ref=f"mock_{uuid.uuid4().hex[:16]}",
            driver_url=f"{self.settings.public_base_url}/demo/driver/{case.id}",
        )

    def completion_delay(self) -> float:
        return random.uniform(self.settings.mock_delay_min_seconds, self.settings.mock_delay_max_seconds)

    def build_completion(self, case: VerificationCase) -> tuple[bytes, dict[str, str]]:
        """The signed webhook the vendor would send when the driver finishes."""
        body = json.dumps(self._payload(case)).encode()
        headers = {"Content-Type": "application/json"}
        headers.update(signed_headers(self.settings.mock_provider_secret, body, SIGNATURE_PREFIX))
        return body, headers

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        return verify_signature(
            self.settings.mock_provider_secret,
            headers.get(f"{SIGNATURE_PREFIX}-Timestamp"),
            body,
            headers.get(f"{SIGNATURE_PREFIX}-Signature"),
            self.settings.request_max_skew_seconds,
        )

    async def parse_webhook(self, body: bytes) -> RtwResult:
        data = json.loads(body)

        def outcome(section: dict[str, Any], **details: Any) -> CheckOutcome:
            return CheckOutcome(CheckStatus(section["status"]), list(section.get("reasons", [])), details)

        def person(section: dict[str, Any]) -> Person | None:
            if not section.get("name"):
                return None
            return Person(section["name"], date.fromisoformat(section["dob"]))

        rtw, document, liveness = data["rtw"], data["document"], data["liveness"]
        evidence = [
            EvidenceFile(item["kind"], item["content_type"], base64.b64decode(item["data_b64"]))
            for item in data.get("evidence", [])
        ]
        expires = date.fromisoformat(rtw["expires_at"]) if rtw.get("expires_at") else None
        return RtwResult(
            event_id=data["event_id"],
            session_ref=data["session_ref"],
            provider_ref=data["check_id"],
            right_to_work=outcome(
                rtw, method=rtw["method"], permission=rtw["permission"], expires_at=rtw.get("expires_at")
            ),
            identity_document=outcome(document, document_type=document["document_type"]),
            liveness=outcome(liveness, score=liveness["score"], threshold=liveness["threshold"]),
            person_on_rtw=person(rtw),
            person_on_document=person(document),
            rtw_expires_at=expires,
            evidence=evidence,
        )

    def _payload(self, case: VerificationCase) -> dict[str, Any]:
        scenario = case.mock_scenario
        driver = case.driver
        today = date.today()
        name = driver.full_name
        if scenario == "name_mismatch":
            name = f"{driver.first_name} {MIDDLE_NAME} {driver.last_name}"
        dob = driver.dob

        if case.route == Route.SHARE_CODE:
            expires = today - timedelta(days=12) if scenario == "rtw_expired" else today + timedelta(days=700)
            rtw: dict[str, Any] = {
                "method": "home_office_online_check",
                "permission": "time_limited",
                "expires_at": expires.isoformat(),
                "status": "pass",
                "reasons": [],
                "name": name,
                "dob": dob,
            }
            if scenario == "rtw_expired":
                rtw["status"] = "fail"
                rtw["reasons"] = [f"Permission to work in the UK ended on {expires:%d %B %Y}."]
            document_type = "uk_driving_licence"
            evidence_kind = EvidenceKind.RTW_PROFILE
            evidence_lines = [
                "SIMULATED - TEST DATA - NOT A HOME OFFICE DOCUMENT",
                "",
                "Right to work profile (mock)",
                f"Name: {name}",
                f"Date of birth: {dob}",
                "Permission: time-limited, can work in the UK",
                f"Valid until: {expires.isoformat()}",
                f"Checked on: {today.isoformat()}",
            ]
        else:
            rtw = {
                "method": "idsp_passport",
                "permission": "unlimited",
                "expires_at": None,
                "status": "pass",
                "reasons": [],
                "name": name,
                "dob": dob,
            }
            document_type = "uk_passport"
            evidence_kind = EvidenceKind.IDSP_REPORT
            evidence_lines = [
                "SIMULATED - TEST DATA - NOT A CERTIFIED IDSP REPORT",
                "",
                "Digital identity check report (mock)",
                f"Name: {name}",
                f"Date of birth: {dob}",
                "Document: British passport, chip read, genuine",
                f"Checked on: {today.isoformat()}",
            ]

        score = 0.62 if scenario == "face_mismatch" else 0.97
        liveness: dict[str, Any] = {"status": "pass", "reasons": [], "score": score, "threshold": FACE_THRESHOLD}
        if score < FACE_THRESHOLD:
            liveness["status"] = "unclear"
            liveness["reasons"] = [
                f"Liveness passed, but the face match score {score:.2f} is below the {FACE_THRESHOLD:.2f} threshold."
            ]

        return {
            "event_id": f"evt_{uuid.uuid4().hex}",
            "type": "check.completed",
            "session_ref": case.rtw_session_ref,
            "check_id": f"chk_{uuid.uuid4().hex[:16]}",
            "rtw": rtw,
            "document": {
                "status": "pass",
                "reasons": [],
                "document_type": document_type,
                "name": name,
                "dob": dob,
            },
            "liveness": liveness,
            "evidence": [
                {
                    "kind": evidence_kind,
                    "content_type": "application/pdf",
                    "data_b64": base64.b64encode(simple_pdf(evidence_lines)).decode(),
                }
            ],
        }
