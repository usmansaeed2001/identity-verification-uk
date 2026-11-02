"""Check Share Code (checksharecode.co.uk): real share code and DVLA check code lookups.

It drives the official gov.uk services in a browser on our behalf. It is not a
registered RtW DVSP, so it does no face matching: a person must compare the
Home Office photo with the driver, which is why an accepted share code comes
back as "unclear" and the case goes to review.

API: https://checksharecode.co.uk/openapi.json
"""

import base64
import logging
import uuid
from datetime import date, datetime
from typing import Any

from app.config import Settings
from app.domain.enums import CheckStatus, EvidenceKind
from app.domain.models import VerificationCase
from app.http import get_http_client
from app.providers.base import (
    CheckOutcome,
    DriverInputError,
    EvidenceFile,
    LicenceResult,
    Person,
    ProviderError,
    ProviderTimeout,
    RtwResult,
    RtwSession,
)

logger = logging.getLogger(__name__)

# Live checks take 15-40 seconds; the API asks for a timeout of at least 60.
REQUEST_TIMEOUT_SECONDS = 75.0
HGV_CATEGORIES = {"C", "CE"}
TRANSIENT_CODES = {"BUSY", "GOVUK_UNEXPECTED", "TIMEOUT", "INTERNAL", "RATE_LIMITED"}

PHOTO_CHECK_REASON = (
    "The Home Office confirms the right to work. Compare the Home Office photo with the driver, "
    "in person or by video call, before approving."
)
IDENTITY_DEFERRED_REASON = (
    "Identity verification isn't switched on yet. The reviewer confirms the Home Office photo matches the driver."
)
CPC_NOT_AVAILABLE_REASON = (
    "DVLA's check code service doesn't show Driver CPC. Check the driver's qualification card (DQC) before approving."
)

RTW_INPUT_MESSAGES = {
    "NOT_FOUND": (
        "The Home Office has no record for that share code and date of birth. "
        "Check both, or get a new share code at gov.uk/prove-right-to-work."
    ),
    "SHARE_CODE_UNUSABLE": (
        "That share code can't be used for a right to work check. It may have expired or be for something else, "
        "such as renting. Get a new right to work share code at gov.uk/prove-right-to-work."
    ),
}
LICENCE_NEW_CODE = "Make a new check code at gov.uk/view-driving-licence and enter it again."
LICENCE_INPUT_MESSAGES = {
    "CHECK_CODE_UNUSABLE": "DVLA didn't accept that licence number and check code. The code may be wrong, "
    "expired or already used. " + LICENCE_NEW_CODE,
    "CHECK_CODE_ALREADY_USED": "That check code has already been used, and each code works once. " + LICENCE_NEW_CODE,
}


# The provider's sandbox test codes. Sent with a live key they'd run a real gov.uk
# check that finds nothing and still uses one of the account's paid checks.
SANDBOX_SHARE_CODES = {"AA1AA1AA1", "BB2BB2BB2", "CC3CC3CC3", "DD4DD4DD4", "EE5EE5EE5", "FF6FF6FF6", "GG7GG7GG7"}
SANDBOX_CHECK_CODE_PREFIXES = {"AAAA", "BBBB", "CCCC", "DDDD", "EEEE", "FFFF", "GGGG"}


def _is_sandbox_test_code(payload: dict[str, Any]) -> bool:
    share_code = str(payload.get("share_code", "")).replace(" ", "").upper()
    check_code = str(payload.get("check_code", "")).replace(" ", "")
    return share_code in SANDBOX_SHARE_CODES or check_code[:4].upper() in SANDBOX_CHECK_CODE_PREFIXES


class CheckShareCodeClient:
    def __init__(self, settings: Settings):
        if not settings.checksharecode_api_key:
            raise ProviderError("CHECKSHARECODE_API_KEY is not set.")
        self.base_url = settings.checksharecode_base_url.rstrip("/")
        self.api_key = settings.checksharecode_api_key
        self.live = not settings.live_providers_are_sandbox

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.live and _is_sandbox_test_code(payload):
            # Refused before anything leaves the process: no gov.uk call, no check used.
            raise DriverInputError("SANDBOX_CODE_ON_LIVE_KEY", "That's a sandbox test code. Enter a real code.")
        try:
            response = await get_http_client().post(
                f"{self.base_url}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # network trouble: worth another try
            raise ProviderTimeout(f"Check Share Code didn't answer: {type(exc).__name__}") from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.is_success:
            return data
        error = data.get("error", {}) if isinstance(data, dict) else {}
        code = error.get("code") or f"HTTP_{response.status_code}"
        message = error.get("message") or f"Check Share Code returned HTTP {response.status_code}."
        logger.warning("Check Share Code %s failed: %s %s", path, response.status_code, code)
        raise _classify(code, message, error.get("check_code_used"), path)


def _classify(code: str, message: str, check_code_used: Any, path: str) -> Exception:
    is_licence = path.endswith("driving-licence")
    if is_licence and code in LICENCE_INPUT_MESSAGES:
        return DriverInputError(code, LICENCE_INPUT_MESSAGES[code])
    if not is_licence and code in RTW_INPUT_MESSAGES:
        return DriverInputError(code, RTW_INPUT_MESSAGES[code])
    if code == "INVALID_INPUT":
        return DriverInputError(code, message)
    if code in TRANSIENT_CODES:
        # A licence check code works once: only retry when DVLA never saw it.
        if is_licence and check_code_used is not False:
            return DriverInputError(
                code, "DVLA didn't answer, and the check code may have been used up. " + LICENCE_NEW_CODE
            )
        return ProviderTimeout(message)
    return ProviderError(f"{code}: {message}")


def _decode_data_url(data_url: str | None) -> bytes | None:
    if not data_url or "," not in data_url:
        return None
    return base64.b64decode(data_url.split(",", 1)[1])


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _still_valid(valid_to: str | None, today: date) -> bool:
    end = _parse_date(valid_to)
    return end is None or end >= today


def _normalise_category(category: str) -> str:
    return category.replace("+", "").strip().upper()


class CheckShareCodeRtwProvider:
    name = "checksharecode"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def create_session(self, case: VerificationCase) -> RtwSession:
        # No hosted vendor page: the host (or our demo pages) collects the share code.
        return RtwSession(
            session_ref=f"csc_{uuid.uuid4().hex[:16]}",
            driver_url=f"{self.settings.public_base_url}/demo/driver/{case.id}",
        )

    async def check_share_code(self, case: VerificationCase, share_code: str, dob: date) -> RtwResult:
        data = await CheckShareCodeClient(self.settings).post(
            "/v1/check/right-to-work",
            {"share_code": share_code, "date_of_birth": dob.isoformat(), "company_name": self.settings.employer_name},
        )
        accepted = data.get("outcome") == "ACCEPTED"
        expires = _parse_date(data.get("expiry_date"))
        recheck = _parse_date(data.get("recheck_date"))
        restrictions = list(data.get("restrictions") or [])
        conditions = list(data.get("conditions") or [])
        if accepted:
            # Conditions can tie the worker to one sponsoring employer, so the reviewer must read them.
            reasons = (
                [PHOTO_CHECK_REASON]
                + [f"Condition: {c}" for c in conditions]
                + [f"Restriction: {r}" for r in restrictions]
            )
            status = CheckStatus.UNCLEAR
        else:
            reasons = [data.get("details") or "The Home Office says this person doesn't have the right to work."]
            status = CheckStatus.FAIL
        details = {
            "method": "home_office_online_check",
            "summary": data.get("details"),
            "expires_at": expires.isoformat() if expires else None,
            "recheck_date": recheck.isoformat() if recheck else None,
            "conditions": conditions,
            "restrictions": restrictions,
            "reference": data.get("reference"),
            "checked_as": data.get("company_name"),
            "checked_at": data.get("checked_at"),
        }
        person_dob = _parse_date(data.get("date_of_birth")) or dob
        evidence = []
        pdf = _decode_data_url(data.get("pdf_data_url"))
        if pdf:
            evidence.append(EvidenceFile(EvidenceKind.RTW_PROFILE, "application/pdf", pdf))
        photo = _decode_data_url(data.get("photo_data_url"))
        if photo:
            evidence.append(EvidenceFile(EvidenceKind.HOME_OFFICE_PHOTO, "image/jpeg", photo))
        return RtwResult(
            event_id=f"csc_{uuid.uuid4().hex}",
            session_ref=case.rtw_session_ref or "",
            provider_ref=data.get("reference") or "",
            right_to_work=CheckOutcome(status, reasons, details),
            identity_document=CheckOutcome(CheckStatus.SKIPPED, [IDENTITY_DEFERRED_REASON]),
            liveness=CheckOutcome(CheckStatus.SKIPPED, [IDENTITY_DEFERRED_REASON]),
            person_on_rtw=Person(data["name"], person_dob) if data.get("name") else None,
            person_on_document=None,
            # The follow-up check is due on gov.uk's recheck date, or when permission ends.
            rtw_expires_at=recheck or expires,
            evidence=evidence,
        )

    def unavailable_result(self, case: VerificationCase, reason: str) -> RtwResult:
        return RtwResult(
            event_id=f"csc_{uuid.uuid4().hex}",
            session_ref=case.rtw_session_ref or "",
            provider_ref="",
            right_to_work=CheckOutcome(CheckStatus.UNCLEAR, [reason]),
            identity_document=CheckOutcome(CheckStatus.SKIPPED, [IDENTITY_DEFERRED_REASON]),
            liveness=CheckOutcome(CheckStatus.SKIPPED, [IDENTITY_DEFERRED_REASON]),
            person_on_rtw=None,
            person_on_document=None,
            rtw_expires_at=None,
        )


class CheckShareCodeLicenceProvider:
    name = "checksharecode_dvla"
    requires_check_code = True

    def __init__(self, settings: Settings):
        self.settings = settings

    async def lookup(self, case: VerificationCase) -> LicenceResult:
        if not case.dvla_check_code:
            raise DriverInputError("NO_CHECK_CODE", "The driver hasn't given a DVLA check code. " + LICENCE_NEW_CODE)
        data = await CheckShareCodeClient(self.settings).post(
            "/v1/check/driving-licence",
            {"licence_number": case.driver.licence_number, "check_code": case.dvla_check_code},
        )
        today = date.today()
        full = sorted(
            {
                _normalise_category(e["category"])
                for e in data.get("entitlements", [])
                if e.get("kind") == "full" and _still_valid(e.get("valid_to"), today)
            }
        )
        status_text = data.get("driving_status") or ""
        flags = {f["code"] for f in data.get("flags", [])}
        points = int(data.get("points") or 0)

        licence = CheckOutcome(CheckStatus.PASS)
        if "disqualif" in status_text.lower():
            licence = CheckOutcome(CheckStatus.FAIL, [f"DVLA shows: {status_text}."])
        elif not HGV_CATEGORIES & set(full):
            licence = CheckOutcome(
                CheckStatus.FAIL, ["The licence has no full entitlement to drive category C or C+E."]
            )
        elif "not_current_full_licence" in flags:
            licence = CheckOutcome(CheckStatus.FAIL, [f"DVLA shows '{status_text}', not a current full licence."])
        elif "points_9_or_more" in flags:
            licence = CheckOutcome(CheckStatus.UNCLEAR, [f"The licence has {points} penalty points."])
        licence.details = {
            "categories": full,
            "points": points,
            "offences": int(data.get("offences") or 0),
            "driving_status": status_text,
            "licence_valid_to": data.get("licence_valid_to"),
            "flags": sorted(flags),
        }

        evidence = []
        pdf = _decode_data_url(data.get("pdf_data_url"))
        if pdf:
            evidence.append(EvidenceFile(EvidenceKind.DVLA_SUMMARY, "application/pdf", pdf))
        return LicenceResult(
            provider_ref=data.get("licence_number_last8") or "",
            licence=licence,
            cpc=CheckOutcome(CheckStatus.UNCLEAR, [CPC_NOT_AVAILABLE_REASON]),
            person=None,  # DVLA's check code service gives no date of birth
            categories=full,
            points=points,
            evidence=evidence,
        )
