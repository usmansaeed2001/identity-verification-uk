"""Demo pages: host simulator, driver screens, and an admin case view.

Mounted only outside production. Mock cases show simulated vendor screens and
ignore what the driver types. Check Share Code cases run real gov.uk checks
(or its sandbox, depending on the API key).
"""

import uuid
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.demo.client import HostApiError, HostClient
from app.domain.enums import DECIDED_STATUSES, CaseStatus, CheckStatus, CheckType, EvidenceKind, Route
from app.domain.models import AuditEvent, Evidence, OutboundWebhook, VerificationCase
from app.domain.validation import validate_dvla_check_code, validate_licence_number, validate_share_code
from app.errors import NotFound
from app.providers import registry
from app.providers.checksharecode import CheckShareCodeRtwProvider
from app.providers.mock_rtw import MockRtwProvider
from app.providers.scenarios import DEFAULT_SCENARIO, SCENARIOS
from app.security import verify_signature
from app.services.notifier import SIGNATURE_PREFIX
from app.services.orchestrator import Orchestrator, load_case
from app.workers.queue import get_queue

router = APIRouter(prefix="/demo", include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

CHECK_LABELS = {
    CheckType.RIGHT_TO_WORK: "Right to work",
    CheckType.IDENTITY_DOCUMENT: "ID document is genuine",
    CheckType.LIVENESS: "Liveness and face match",
    CheckType.NAME_DOB_MATCH: "Name and date of birth agree",
    CheckType.DVLA_LICENCE: "Licence valid for C or C+E",
    CheckType.DRIVER_CPC: "Driver CPC valid",
}
OUTCOMES = {
    CaseStatus.PASSED: ("Cleared to drive", "All checks passed."),
    CaseStatus.FAILED: ("Not cleared", "At least one check failed."),
    CaseStatus.MANUAL_REVIEW: ("Waiting for a person to review", "Something couldn't be confirmed automatically."),
}
EVIDENCE_LABELS = {
    EvidenceKind.RTW_PROFILE: "Home Office right to work profile",
    EvidenceKind.IDSP_REPORT: "Identity provider report",
    EvidenceKind.HOME_OFFICE_PHOTO: "Home Office photo",
    EvidenceKind.DVLA_SUMMARY: "DVLA driving licence summary",
}
STEP_TITLES = {
    "consent": "Before you start",
    "document": "Photograph your document",
    "selfie": "Take a selfie",
    "share-code": "Your share code",
    "licence": "Your driving licence",
}
DEMO_DEFAULTS = {
    "first_name": "Tomasz",
    "last_name": "Nowak",
    "dob": "1987-03-14",
    "licence_number": "NOWAK803147T99AB",
}


def _fmt_dt(value: Any) -> str:
    return value.strftime("%d %b %Y, %H:%M:%S UTC") if value else ""


def _fmt_date(value: Any) -> str:
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime("%d %b %Y") if value else ""


templates.env.filters["dt"] = _fmt_dt
templates.env.filters["d"] = _fmt_date
templates.env.globals.update(
    CHECK_LABELS=CHECK_LABELS, OUTCOMES=OUTCOMES, EVIDENCE_LABELS=EVIDENCE_LABELS, CheckStatus=CheckStatus
)


def driver_steps(case: VerificationCase) -> list[str]:
    if registry.collects_share_code(case):
        # Real checks: identity (document + selfie) is deferred, so only the two codes.
        return ["consent", "share-code", "licence"]
    steps = ["consent", "document", "selfie"]
    if case.route == Route.SHARE_CODE:
        steps.append("share-code")
    steps.append("licence")
    return steps


def check_facts(check) -> list[str]:
    """Short human-readable facts from a check's provider details, for the admin view."""
    d = check.details or {}
    facts = []
    match CheckType(check.type):
        case CheckType.RIGHT_TO_WORK:
            if d.get("method"):
                facts.append(
                    "Home Office online check"
                    if d["method"] == "home_office_online_check"
                    else "Certified IDSP passport check"
                )
            if d.get("summary"):
                facts.append(d["summary"])
            if d.get("permission"):
                facts.append(f"Permission: {d['permission'].replace('_', '-')}")
            if d.get("expires_at"):
                facts.append(f"Valid until {_fmt_date(d['expires_at'])}")
            if d.get("recheck_date"):
                facts.append(f"Check again by {_fmt_date(d['recheck_date'])}")
            facts.extend(f"Condition: {c}" for c in d.get("conditions", []))
            if d.get("reference"):
                facts.append(f"Home Office reference {d['reference']}")
        case CheckType.IDENTITY_DOCUMENT:
            if d.get("document_type"):
                facts.append(d["document_type"].replace("_", " ").replace("uk", "UK"))
        case CheckType.LIVENESS:
            if "score" in d:
                facts.append(f"Face match {d['score']:.2f} (threshold {d['threshold']:.2f})")
        case CheckType.NAME_DOB_MATCH:
            if d.get("sources"):
                facts.append("Compared with: " + ", ".join(d["sources"]))
        case CheckType.DVLA_LICENCE:
            if d.get("categories"):
                facts.append("Categories: " + ", ".join(c.replace("CE", "C+E") for c in d["categories"]))
            if d.get("driving_status"):
                facts.append(f"DVLA: {d['driving_status']}")
            if "points" in d:
                facts.append(f"{d['points']} penalty points")
        case CheckType.DRIVER_CPC:
            if d.get("dqc_expires_at"):
                facts.append(f"DQC valid until {_fmt_date(d['dqc_expires_at'])}")
    return facts


templates.env.globals["check_facts"] = check_facts


DEMO_DRIVEN_PROVIDERS = {MockRtwProvider.name, CheckShareCodeRtwProvider.name}


async def _demo_case(session: AsyncSession, case_id: uuid.UUID) -> VerificationCase:
    case = await load_case(session, case_id)
    if case.rtw_provider not in DEMO_DRIVEN_PROVIDERS:
        raise NotFound("This verification is completed in the provider's own app, not here.")
    return case


def _not_found(request: Request, message: str) -> HTMLResponse:
    return templates.TemplateResponse(request, "error.html", {"message": message}, status_code=404)


# --- Host simulator --------------------------------------------------------


def _start_context(request: Request, values: dict[str, str] | None = None, error: HostApiError | None = None):
    settings = request.app.state.settings
    return {
        "values": {**DEMO_DEFAULTS, "route": Route.SHARE_CODE, "scenario": DEFAULT_SCENARIO, **(values or {})},
        "scenarios": SCENARIOS.values(),
        "live_available": settings.live_providers_configured,
        "live_sandbox": settings.live_providers_are_sandbox,
        "error": error,
    }


@router.get("", response_class=HTMLResponse)
async def start_page(request: Request):
    return templates.TemplateResponse(request, "start.html", _start_context(request))


@router.post("/start")
async def start_verification(
    request: Request,
    first_name: str = Form(""),
    last_name: str = Form(""),
    dob: str = Form(""),
    route: str = Form(Route.SHARE_CODE),
    mode: str = Form("mock"),
    scenario: str = Form(DEFAULT_SCENARIO),
):
    settings = request.app.state.settings
    values = {"first_name": first_name, "last_name": last_name, "dob": dob, "route": route, "scenario": scenario}
    payload = {
        "external_driver_id": f"demo-{uuid.uuid4().hex[:8]}",
        "first_name": first_name,
        "last_name": last_name,
        "dob": dob,
        "route": route,
        "mode": mode,
        "callback_url": f"{settings.internal_base_url}/demo/host-webhook",
    }
    if mode == "mock":
        payload["mock_scenario"] = scenario
    try:
        async with HostClient(request.app, settings) as host:
            created = await host.create_verification(payload)
    except HostApiError as exc:
        return templates.TemplateResponse(
            request, "start.html", _start_context(request, values, exc), status_code=exc.status_code
        )
    if "/demo/driver/" not in (created["driver_url"] or ""):
        return RedirectResponse(created["driver_url"], status_code=303)
    # Our own driver pages: a same-origin path works whatever host the browser used.
    return RedirectResponse(f"/demo/driver/{created['id']}", status_code=303)


@router.post("/host-webhook")
async def host_webhook_receiver(request: Request):
    """Stands in for the host's webhook endpoint and checks our signature like a host would."""
    settings = request.app.state.settings
    body = await request.body()
    valid = verify_signature(
        settings.webhook_signing_secret,
        request.headers.get(f"{SIGNATURE_PREFIX}-Timestamp"),
        body,
        request.headers.get(f"{SIGNATURE_PREFIX}-Signature"),
        settings.request_max_skew_seconds,
    )
    if not valid:
        return JSONResponse({"received": False, "error": "bad signature"}, status_code=401)
    return {"received": True}


# --- Driver journey ------------------------------------------------------------
# Mock cases: simulated vendor screens. Check Share Code cases: real forms whose
# share code and DVLA check code go to gov.uk through the provider.


@router.get("/driver/{case_id}")
async def driver_entry(request: Request, case_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    try:
        case = await _demo_case(session, case_id)
    except NotFound as exc:
        return _not_found(request, exc.message)
    if case.status != CaseStatus.AWAITING_DRIVER or case.rtw_share_code:
        return RedirectResponse(f"/demo/driver/{case_id}/checking", status_code=303)
    return RedirectResponse(f"/demo/driver/{case_id}/consent", status_code=303)


def _render_step(
    request: Request,
    case: VerificationCase,
    step: str,
    errors: dict[str, str] | None = None,
    values: dict[str, str] | None = None,
    status_code: int = 200,
):
    steps = driver_steps(case)
    return templates.TemplateResponse(
        request,
        f"driver_{step.replace('-', '_')}.html",
        {
            "case": case,
            "step": step,
            "step_number": steps.index(step) + 1,
            "step_count": len(steps),
            "title": STEP_TITLES[step],
            "errors": errors or {},
            "values": values or {},
            "is_passport": case.route == Route.BRITISH_IRISH,
            **_journey_flags(case),
        },
        status_code=status_code,
    )


def _journey_flags(case: VerificationCase) -> dict[str, bool]:
    real = registry.collects_share_code(case)
    return {"real": real, "sandbox": real and case.is_test}


def _next_step(case: VerificationCase, step: str) -> RedirectResponse:
    steps = driver_steps(case)
    index = steps.index(step)
    target = steps[index + 1] if index + 1 < len(steps) else "checking"
    return RedirectResponse(f"/demo/driver/{case.id}/{target}", status_code=303)


@router.get("/driver/{case_id}/checking", response_class=HTMLResponse)
async def driver_checking(request: Request, case_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    try:
        case = await _demo_case(session, case_id)
    except NotFound as exc:
        return _not_found(request, exc.message)
    return templates.TemplateResponse(request, "driver_checking.html", _status_context(case))


@router.get("/driver/{case_id}/status", response_class=HTMLResponse)
async def driver_status(request: Request, case_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    try:
        case = await _demo_case(session, case_id)
    except NotFound as exc:
        return _not_found(request, exc.message)
    return templates.TemplateResponse(request, "_driver_status.html", _status_context(case))


ACTION_STEPS = {CheckType.RIGHT_TO_WORK: "share-code", CheckType.DVLA_LICENCE: "licence"}


def _status_context(case: VerificationCase) -> dict[str, Any]:
    checks = case.ordered_checks()
    # Checks the provider bounced back to the driver (a share code or check code it couldn't use).
    actions = [
        {"step": ACTION_STEPS[CheckType(c.type)], "message": c.reasons[0] if c.reasons else ""}
        for c in checks
        if c.status == CheckStatus.PENDING and c.details and "input_error" in c.details
    ]
    return {
        "case": case,
        "decided": case.status in DECIDED_STATUSES,
        "checks": checks,
        "actions": actions,
        **_journey_flags(case),
    }


@router.get("/driver/{case_id}/{step}", response_class=HTMLResponse)
async def driver_step(request: Request, case_id: uuid.UUID, step: str, session: AsyncSession = Depends(get_session)):
    try:
        case = await _demo_case(session, case_id)
    except NotFound as exc:
        return _not_found(request, exc.message)
    if step not in driver_steps(case):
        return _not_found(request, "That step doesn't exist for this verification.")
    values = (
        {"licence_number": case.driver.licence_number or DEMO_DEFAULTS["licence_number"]} if step == "licence" else {}
    )
    return _render_step(request, case, step, values=values)


@router.post("/driver/{case_id}/{step}")
async def driver_step_submit(
    request: Request, case_id: uuid.UUID, step: str, session: AsyncSession = Depends(get_session)
):
    try:
        case = await _demo_case(session, case_id)
    except NotFound as exc:
        return _not_found(request, exc.message)
    if step not in driver_steps(case):
        return _not_found(request, "That step doesn't exist for this verification.")
    real = registry.collects_share_code(case)
    # Real cases reopen the share code or licence step when gov.uk refused a code.
    if case.status in DECIDED_STATUSES or (not real and case.status != CaseStatus.AWAITING_DRIVER):
        return RedirectResponse(f"/demo/driver/{case_id}/checking", status_code=303)
    form = await request.form()
    settings = request.app.state.settings

    if step == "consent":
        if form.get("agree") != "yes":
            return _render_step(
                request, case, step, {"agree": "Tick the box to agree before you continue."}, status_code=422
            )
        scope = (
            ["home_office_share_code_check", "dvla_licence_check"]
            if real
            else ["identity_document", "biometric_selfie"]
        )
        await Orchestrator(session).record_driver_consent(case, scope)

    elif step == "share-code":
        raw = str(form.get("share_code", ""))
        errors = {}
        try:
            share_code = validate_share_code(raw, require_w_prefix=not _journey_flags(case)["sandbox"])
        except ValueError as exc:
            errors["share_code"] = str(exc)
        try:
            dob = date.fromisoformat(str(form.get("dob", "")))
        except ValueError:
            errors["dob"] = "Enter your date of birth."
        if errors:
            return _render_step(request, case, step, errors, {"share_code": raw}, 422)
        if real:
            try:
                async with HostClient(request.app, settings) as host:
                    await host.submit_share_code(str(case.id), share_code, dob)
            except HostApiError as exc:
                if exc.status_code != 409:
                    return _render_step(request, case, step, {"share_code": exc.message}, {"share_code": raw}, 422)
            # Back to the status page if this was a second try after gov.uk refused the first code.
            if case.check(CheckType.DVLA_LICENCE).completed_at or case.dvla_consent_at:
                return RedirectResponse(f"/demo/driver/{case_id}/checking", status_code=303)
        # Mock cases: validated for realism, then thrown away.

    elif step == "licence":
        raw = str(form.get("licence_number", ""))
        raw_code = str(form.get("check_code", ""))
        errors = {}
        try:
            licence_number = validate_licence_number(raw)
        except ValueError as exc:
            errors["licence_number"] = str(exc)
        check_code = None
        if real:
            try:
                check_code = validate_dvla_check_code(raw_code)
            except ValueError as exc:
                errors["check_code"] = str(exc)
        if form.get("dvla_consent") != "yes":
            errors["dvla_consent"] = "Tick the box to agree to the DVLA check."
        values = {"licence_number": raw, "check_code": raw_code}
        if errors:
            return _render_step(request, case, step, errors, values, 422)
        try:
            async with HostClient(request.app, settings) as host:
                await host.submit_licence(str(case.id), licence_number, check_code)
        except HostApiError as exc:
            if exc.status_code != 409:
                field = "check_code" if "check_code" in exc.fields else "licence_number"
                return _render_step(request, case, step, {field: exc.fields.get(field) or exc.message}, values, 422)
        if not real:
            # The simulated vendor now "finishes" and reports back by webhook after a short delay.
            provider = MockRtwProvider(settings)
            await get_queue().enqueue(
                "deliver_mock_rtw_webhook", defer_by=provider.completion_delay(), case_id=str(case.id)
            )

    return _next_step(case, step)


# --- Admin case view ---------------------------------------------------------


@router.get("/admin", response_class=HTMLResponse)
async def admin_list(request: Request, session: AsyncSession = Depends(get_session)):
    cases = (
        (await session.execute(select(VerificationCase).order_by(VerificationCase.created_at.desc()).limit(50)))
        .scalars()
        .all()
    )
    return templates.TemplateResponse(request, "admin_list.html", {"cases": cases, "scenarios": SCENARIOS})


async def _admin_context(session: AsyncSession, case: VerificationCase) -> dict[str, Any]:
    max_attempts = get_settings().webhook_max_attempts
    webhooks = (
        (
            await session.execute(
                select(OutboundWebhook).where(OutboundWebhook.case_id == case.id).order_by(OutboundWebhook.created_at)
            )
        )
        .scalars()
        .all()
    )
    events = (
        (await session.execute(select(AuditEvent).where(AuditEvent.case_id == case.id).order_by(AuditEvent.id)))
        .scalars()
        .all()
    )
    evidence = (
        (await session.execute(select(Evidence).where(Evidence.case_id == case.id).order_by(Evidence.created_at)))
        .scalars()
        .all()
    )
    webhooks_pending = any(w.delivered_at is None and w.attempts < max_attempts for w in webhooks)
    return {
        "case": case,
        "checks": case.ordered_checks(),
        "webhooks": webhooks,
        "events": events,
        "evidence": evidence,
        "photo": next((e for e in evidence if e.kind == EvidenceKind.HOME_OFFICE_PHOTO), None),
        "scenario": SCENARIOS.get(case.mock_scenario or ""),
        "live": case.status not in DECIDED_STATUSES or webhooks_pending,
    }


@router.get("/admin/cases/{case_id}", response_class=HTMLResponse)
async def admin_case(request: Request, case_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    try:
        case = await load_case(session, case_id)
    except NotFound as exc:
        return _not_found(request, exc.message)
    return templates.TemplateResponse(request, "admin_case.html", await _admin_context(session, case))


@router.get("/admin/cases/{case_id}/panel", response_class=HTMLResponse)
async def admin_case_panel(request: Request, case_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    try:
        case = await load_case(session, case_id)
    except NotFound as exc:
        return _not_found(request, exc.message)
    return templates.TemplateResponse(request, "_admin_panel.html", await _admin_context(session, case))


@router.post("/admin/cases/{case_id}/review")
async def admin_review(
    request: Request,
    case_id: uuid.UUID,
    decision: str = Form(...),
    note: str = Form(""),
    reviewed_by: str = Form("Demo reviewer"),
    session: AsyncSession = Depends(get_session),
):
    try:
        async with HostClient(request.app, request.app.state.settings) as host:
            await host.review(str(case_id), decision, note, reviewed_by)
    except HostApiError as exc:
        case = await load_case(session, case_id)
        context = await _admin_context(session, case)
        context["review_error"] = exc.fields.get("note") or exc.message
        context["review_note"] = note
        return templates.TemplateResponse(request, "admin_case.html", context, status_code=exc.status_code)
    return RedirectResponse(f"/demo/admin/cases/{case_id}", status_code=303)


@router.get("/admin/cases/{case_id}/evidence/{evidence_id}")
async def admin_evidence(request: Request, case_id: uuid.UUID, evidence_id: uuid.UUID):
    async with HostClient(request.app, request.app.state.settings) as host:
        items = await host.evidence(str(case_id))
    for item in items:
        if item["id"] == str(evidence_id):
            # Same-origin path, so the link works whatever host the browser used.
            url = item["url"]
            return RedirectResponse(url[url.index("/v1/") :], status_code=303)
    return _not_found(request, "Evidence not found.")
