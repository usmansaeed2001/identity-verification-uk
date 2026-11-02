"""Moves a verification case through its checks and decides the outcome.

State changes that could race (two handlers finishing at once) use
conditional UPDATEs, so only one of them wins and the host gets one webhook.
"""

import logging
import uuid
from datetime import date, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import utcnow
from app.domain.decision import IdentitySource, compare_identity, decide
from app.domain.enums import (
    DECIDED_STATUSES,
    FINISHED_STATUSES,
    CaseStatus,
    CheckStatus,
    CheckType,
    Mode,
    ReviewDecision,
    Route,
    WebhookEvent,
)
from app.domain.models import Check, Driver, Evidence, VerificationCase
from app.domain.schemas import CreateVerificationRequest
from app.domain.validation import mask, validate_share_code
from app.errors import Conflict, Forbidden, InvalidRequest, NotFound, ProviderNotConfigured
from app.providers import registry
from app.providers.base import CheckOutcome, EvidenceFile, LicenceResult, Person, RtwResult
from app.providers.scenarios import DEFAULT_SCENARIO, get_scenario
from app.services import notifier
from app.services.audit import audit
from app.services.evidence_store import get_evidence_store
from app.workers.queue import JobQueue, get_queue

logger = logging.getLogger(__name__)

# DVLA data is never used here: DVLA's terms forbid using it for identity checking.
SOURCE_LABELS = {
    CheckType.RIGHT_TO_WORK: "right to work record",
    CheckType.IDENTITY_DOCUMENT: "identity document",
}


async def load_case(session: AsyncSession, case_id: uuid.UUID, *, for_update: bool = False) -> VerificationCase:
    stmt = select(VerificationCase).where(VerificationCase.id == case_id)
    if for_update:
        stmt = stmt.with_for_update()
    case = (await session.execute(stmt)).scalar_one_or_none()
    if case is None:
        raise NotFound("Verification not found.")
    return case


class Orchestrator:
    def __init__(self, session: AsyncSession, settings: Settings | None = None, queue: JobQueue | None = None):
        self.session = session
        self.settings = settings or get_settings()
        self.queue = queue or get_queue()

    # --- Creating a case -------------------------------------------------

    async def create_case(self, req: CreateVerificationRequest) -> VerificationCase:
        mock = req.mode is Mode.MOCK
        if mock and self.settings.is_production:
            raise Forbidden("Mock mode is not available in production.")
        if not mock:
            if req.mock_scenario:
                raise InvalidRequest('mock_scenario can only be used with mode "mock".')
            if not self.settings.live_providers_configured:
                raise ProviderNotConfigured(
                    'No live verification provider is configured yet. Use mode "mock" outside production.'
                )
            if req.route == Route.BRITISH_IRISH:
                raise InvalidRequest(
                    "British and Irish passport checks need a registered identity provider, which isn't connected "
                    'yet. Use route "share_code", or mode "mock".'
                )
        scenario = get_scenario(req.mock_scenario or DEFAULT_SCENARIO, req.route) if mock else None
        rtw_name, licence_name = registry.provider_names(mock, self.settings)
        # Sandbox keys never reach gov.uk, so their results are test data too.
        is_test = mock or self.settings.live_providers_are_sandbox

        driver = await self._upsert_driver(req)
        case = VerificationCase(
            id=uuid.uuid4(),
            driver=driver,
            route=req.route,
            status=CaseStatus.CREATED,
            is_test=is_test,
            mock_scenario=scenario.key if scenario else None,
            rtw_provider=rtw_name,
            licence_provider=licence_name,
            callback_url=str(req.callback_url) if req.callback_url else None,
            dvla_consent_at=utcnow() if req.licence_number and req.dvla_consent else None,
            checks=[Check(type=t, status=CheckStatus.PENDING, reasons=[]) for t in CheckType],
        )
        self.session.add(case)
        # Audit rows reference the case by FK only, so the case row must exist first.
        await self.session.flush()
        audit(
            self.session,
            case.id,
            "host",
            "case.created",
            route=req.route,
            mode=req.mode,
            scenario=case.mock_scenario,
            licence_number=mask(req.licence_number),
            dvla_consent=bool(case.dvla_consent_at),
        )

        rtw = registry.rtw_for_case(case, self.settings)
        session = await rtw.create_session(case)
        case.rtw_session_ref = session.session_ref
        case.driver_url = session.driver_url
        case.status = CaseStatus.AWAITING_DRIVER
        audit(self.session, case.id, "system", "rtw.session_started", provider=rtw.name)
        await self.session.commit()
        return case

    async def _upsert_driver(self, req: CreateVerificationRequest) -> Driver:
        driver = (
            await self.session.execute(select(Driver).where(Driver.external_driver_id == req.external_driver_id))
        ).scalar_one_or_none()
        if driver is None:
            driver = Driver(external_driver_id=req.external_driver_id)
            self.session.add(driver)
        driver.first_name = req.first_name
        driver.last_name = req.last_name
        driver.dob = req.dob.isoformat()
        if req.licence_number:
            driver.licence_number = req.licence_number
        return driver

    # --- Driver and provider events ---------------------------------------

    async def record_driver_consent(self, case: VerificationCase, scope: list[str]) -> None:
        audit(self.session, case.id, "driver", "driver.consent_given", scope=scope)
        await self.session.commit()

    async def submit_share_code(self, case: VerificationCase, share_code: str, dob: date) -> None:
        """Run a share code check through a provider we call directly (not a hosted vendor)."""
        if not registry.collects_share_code(case):
            raise Conflict("This verification's provider collects the share code in its own app.")
        if case.status in DECIDED_STATUSES:
            raise Conflict("This verification has already been decided.")
        if case.check(CheckType.RIGHT_TO_WORK).status != CheckStatus.PENDING:
            raise Conflict("The right to work check has already finished.")
        if case.rtw_share_code is not None:
            raise Conflict("A share code check is already running.")
        if not case.is_test:
            try:
                validate_share_code(share_code)
            except ValueError as exc:
                raise InvalidRequest(str(exc)) from exc
        case.rtw_share_code = share_code
        case.rtw_share_code_dob = dob.isoformat()
        audit(self.session, case.id, "host", "share_code.submitted", share_code=mask(share_code, keep=1))
        await self.session.commit()
        await self.queue.enqueue("rtw_share_code_check", case_id=str(case.id))

    async def record_rtw_input_error(self, case: VerificationCase, code: str, message: str) -> None:
        """The provider couldn't use the share code: keep the check open for the driver to try again."""
        check = case.check(CheckType.RIGHT_TO_WORK)
        check.reasons = [message]
        check.details = {"input_error": code}
        case.rtw_share_code = None
        case.rtw_share_code_dob = None
        audit(self.session, case.id, f"provider:{case.rtw_provider}", "share_code.rejected", code=code)
        await self._notify(case, WebhookEvent.DRIVER_ACTION_REQUIRED)

    async def submit_licence(self, case: VerificationCase, licence_number: str, check_code: str | None = None) -> None:
        if case.status in DECIDED_STATUSES:
            raise Conflict("This verification has already been decided.")
        if case.dvla_requested_at is not None:
            raise Conflict("The licence check has already started.")
        if registry.licence_for_case(case, self.settings).requires_check_code and not check_code:
            raise InvalidRequest(
                "This licence check needs the DVLA check code the driver made at gov.uk/view-driving-licence."
            )
        case.driver.licence_number = licence_number
        case.dvla_check_code = check_code
        case.dvla_consent_at = utcnow()
        audit(
            self.session, case.id, "host", "licence.submitted", licence_number=mask(licence_number), dvla_consent=True
        )
        await self.session.commit()
        await self._maybe_start_dvla(case)

    async def record_licence_input_error(self, case: VerificationCase, code: str, message: str) -> None:
        """DVLA refused the check code: reopen the licence step so the driver can send a new one."""
        check = case.check(CheckType.DVLA_LICENCE)
        check.reasons = [message]
        check.details = {"input_error": code}
        case.dvla_check_code = None
        case.dvla_requested_at = None
        audit(self.session, case.id, f"provider:{case.licence_provider}", "licence.check_code_rejected", code=code)
        await self._notify(case, WebhookEvent.DRIVER_ACTION_REQUIRED)

    async def handle_rtw_result(self, case: VerificationCase, result: RtwResult) -> None:
        if case.check(CheckType.RIGHT_TO_WORK).status != CheckStatus.PENDING:
            logger.info("Ignoring second RTW result for case %s", case.id)
            return
        provider = case.rtw_provider
        rtw_details = dict(result.right_to_work.details)
        if result.person_on_rtw:
            rtw_details["person"] = result.person_on_rtw.to_dict()
        doc_details = dict(result.identity_document.details)
        if result.person_on_document:
            doc_details["person"] = result.person_on_document.to_dict()

        self._set_check(
            case,
            CheckType.RIGHT_TO_WORK,
            CheckOutcome(result.right_to_work.status, result.right_to_work.reasons, rtw_details),
            provider,
            result.provider_ref,
        )
        self._set_check(
            case,
            CheckType.IDENTITY_DOCUMENT,
            CheckOutcome(result.identity_document.status, result.identity_document.reasons, doc_details),
            provider,
            result.provider_ref,
        )
        self._set_check(case, CheckType.LIVENESS, result.liveness, provider, result.provider_ref)
        case.rtw_expires_at = result.rtw_expires_at
        case.rtw_share_code = None
        case.rtw_share_code_dob = None
        await self._store_evidence(case, result.evidence)

        if case.status == CaseStatus.AWAITING_DRIVER:
            case.status = CaseStatus.IN_PROGRESS
        audit(
            self.session,
            case.id,
            f"provider:{provider}",
            "rtw.result_received",
            right_to_work=result.right_to_work.status,
            identity_document=result.identity_document.status,
            liveness=result.liveness.status,
            evidence_files=len(result.evidence),
        )
        await self.session.commit()

        if await self.finalize(case):
            return
        await self._maybe_start_dvla(case)

    async def _store_evidence(self, case: VerificationCase, files: list[EvidenceFile]) -> None:
        store = get_evidence_store(self.settings)
        retain_until = utcnow() + timedelta(hours=self.settings.test_case_retention_hours) if case.is_test else None
        for item in files:
            evidence_id = uuid.uuid4()
            key = f"{case.id}/{evidence_id}"
            await store.put(key, item.data)
            self.session.add(
                Evidence(
                    id=evidence_id,
                    case_id=case.id,
                    kind=item.kind,
                    content_type=item.content_type,
                    storage_key=key,
                    size_bytes=len(item.data),
                    retain_until=retain_until,
                )
            )

    async def _maybe_start_dvla(self, case: VerificationCase) -> None:
        """Start the DVLA lookup once the RTW result is in and the driver has consented.

        Called after our own commit by both the share code job and the licence
        submission. Each reads the other's committed changes fresh from the
        database, so whichever finishes last starts the lookup.
        """
        fresh = (
            await self.session.execute(
                select(VerificationCase.status, VerificationCase.dvla_consent_at, Driver.licence_number, Check.status)
                .join(Driver, Driver.id == VerificationCase.driver_id)
                .join(Check, (Check.case_id == VerificationCase.id) & (Check.type == CheckType.RIGHT_TO_WORK))
                .where(VerificationCase.id == case.id)
            )
        ).one()
        status, consent_at, licence_number, rtw_status = fresh
        ready = licence_number and consent_at and rtw_status != CheckStatus.PENDING and status not in DECIDED_STATUSES
        if not ready:
            return
        claimed = await self.session.execute(
            update(VerificationCase)
            .where(VerificationCase.id == case.id, VerificationCase.dvla_requested_at.is_(None))
            .values(dvla_requested_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            return
        audit(self.session, case.id, "system", "dvla.lookup_requested", provider=case.licence_provider)
        await self.session.commit()
        await self.queue.enqueue("dvla_lookup", case_id=str(case.id))

    async def apply_licence_result(
        self, case: VerificationCase, result: LicenceResult | None, failure_reason: str | None = None
    ) -> None:
        if case.status in DECIDED_STATUSES:
            return
        provider = case.licence_provider
        if result is None:
            reason = failure_reason or "The DVLA lookup failed."
            self._set_check(case, CheckType.DVLA_LICENCE, CheckOutcome(CheckStatus.UNCLEAR, [reason]), provider, None)
            self._set_check(
                case,
                CheckType.DRIVER_CPC,
                CheckOutcome(CheckStatus.UNCLEAR, ["Driver CPC couldn't be checked because the DVLA lookup failed."]),
                provider,
                None,
            )
            audit(self.session, case.id, f"provider:{provider}", "dvla.lookup_failed", reason=reason)
        else:
            licence_details = dict(result.licence.details)
            if result.person:
                licence_details["person"] = result.person.to_dict()
            self._set_check(
                case,
                CheckType.DVLA_LICENCE,
                CheckOutcome(result.licence.status, result.licence.reasons, licence_details),
                provider,
                result.provider_ref,
            )
            self._set_check(case, CheckType.DRIVER_CPC, result.cpc, provider, result.provider_ref)
            await self._store_evidence(case, result.evidence)
            audit(
                self.session,
                case.id,
                f"provider:{provider}",
                "dvla.result_received",
                licence=result.licence.status,
                cpc=result.cpc.status,
                categories=result.categories,
                points=result.points,
            )
        case.dvla_check_code = None
        self._run_identity_match(case)
        await self.session.commit()
        await self.finalize(case)

    def _run_identity_match(self, case: VerificationCase) -> None:
        sources = []
        for check_type, label in SOURCE_LABELS.items():
            details = case.check(check_type).details or {}
            if "person" in details:
                person = Person.from_dict(details["person"])
                sources.append(IdentitySource(label, person.full_name, person.dob))
        driver = case.driver
        status, reasons = compare_identity(driver.first_name, driver.last_name, driver.date_of_birth, sources)
        self._set_check(
            case,
            CheckType.NAME_DOB_MATCH,
            CheckOutcome(status, reasons, {"sources": [s.label for s in sources]}),
            "internal",
            None,
        )

    def _set_check(
        self,
        case: VerificationCase,
        check_type: CheckType,
        outcome: CheckOutcome,
        provider: str | None,
        provider_ref: str | None,
    ) -> None:
        check = case.check(check_type)
        check.status = outcome.status
        check.reasons = list(outcome.reasons)
        check.details = outcome.details or None
        check.provider = provider
        check.provider_ref = provider_ref
        check.completed_at = utcnow()

    # --- Deciding ---------------------------------------------------------

    async def finalize(self, case: VerificationCase) -> bool:
        """Apply the decision rules. Returns True when the case reached a decision."""
        if case.status in DECIDED_STATUSES:
            return True
        decision = decide(case.checks)
        if decision.status not in DECIDED_STATUSES:
            return False
        if decision.status == CaseStatus.FAILED:
            for check in case.checks:
                if check.status == CheckStatus.PENDING:
                    check.status = CheckStatus.SKIPPED
                    check.reasons = ["Not run because another check failed."]
        if not await self._transition(case, decision.status):
            return True
        audit(self.session, case.id, "system", "case.decided", status=decision.status, reasons=decision.reasons)
        event = WebhookEvent.REQUIRES_REVIEW if decision.status == CaseStatus.MANUAL_REVIEW else WebhookEvent.COMPLETED
        await self._notify(case, event)
        return True

    async def record_review(
        self, case: VerificationCase, decision: ReviewDecision, note: str, reviewed_by: str
    ) -> None:
        if case.status != CaseStatus.MANUAL_REVIEW:
            raise Conflict("Only verifications waiting for manual review can be reviewed.")
        new_status = CaseStatus.PASSED if decision == ReviewDecision.APPROVE else CaseStatus.FAILED
        if not await self._transition(case, new_status):
            raise Conflict("This verification was reviewed by someone else at the same time.")
        case.review_decision = decision
        case.review_note = note
        case.reviewed_by = reviewed_by
        case.reviewed_at = utcnow()
        audit(self.session, case.id, f"reviewer:{reviewed_by}", "review.recorded", decision=decision, note=note)
        await self._notify(case, WebhookEvent.COMPLETED)

    async def _transition(self, case: VerificationCase, new_status: CaseStatus) -> bool:
        now = utcnow()
        values = {"status": new_status, "updated_at": now}
        if new_status in FINISHED_STATUSES:
            values["completed_at"] = now
        result = await self.session.execute(
            update(VerificationCase)
            .where(VerificationCase.id == case.id, VerificationCase.status == case.status)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            await self.session.rollback()
            return False
        case.status = new_status
        case.updated_at = now
        if new_status in FINISHED_STATUSES:
            case.completed_at = now
        return True

    async def _notify(self, case: VerificationCase, event: WebhookEvent) -> None:
        webhook = notifier.queue_webhook(self.session, case, event, self.settings)
        await self.session.commit()
        if webhook is not None:
            await self.queue.enqueue("deliver_host_webhook", webhook_id=str(webhook.id))
