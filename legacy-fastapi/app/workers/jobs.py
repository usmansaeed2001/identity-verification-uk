"""Background jobs. Each takes arq's ctx dict first, so both queue backends can run them."""

import logging
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, select

from app.config import get_settings
from app.db import session_factory, utcnow
from app.domain.enums import DECIDED_STATUSES, CaseStatus, CheckStatus, CheckType, WebhookEvent
from app.domain.models import Evidence, OutboundWebhook, VerificationCase
from app.errors import NotFound
from app.http import get_http_client
from app.providers import registry
from app.providers.base import DriverInputError, ProviderError, ProviderTimeout
from app.providers.mock_rtw import MockRtwProvider
from app.services import notifier
from app.services.audit import audit
from app.services.evidence_store import get_evidence_store
from app.services.orchestrator import Orchestrator, load_case
from app.workers.queue import get_queue

logger = logging.getLogger(__name__)

DVLA_MAX_ATTEMPTS = 3
RTW_MAX_ATTEMPTS = 3


async def deliver_mock_rtw_webhook(ctx: dict[str, Any], case_id: str) -> None:
    """Play the mock vendor: send its signed completion webhook to our own endpoint."""
    settings = get_settings()
    async with session_factory()() as session:
        case = await load_case(session, uuid.UUID(case_id))
        if case.rtw_provider != MockRtwProvider.name:
            return
        body, headers = MockRtwProvider(settings).build_completion(case)
    url = f"{settings.internal_base_url}/webhooks/{MockRtwProvider.name}"
    response = await get_http_client().post(url, content=body, headers=headers)
    if not response.is_success:
        logger.error("Mock vendor webhook for case %s was rejected: HTTP %s", case_id, response.status_code)


async def rtw_share_code_check(ctx: dict[str, Any], case_id: str, attempt: int = 1) -> None:
    """Check the share code the driver gave us with the Home Office, through the provider."""
    settings = get_settings()
    async with session_factory()() as session:
        try:
            case = await load_case(session, uuid.UUID(case_id))
        except NotFound:
            return
        if case.status in DECIDED_STATUSES or case.check(CheckType.RIGHT_TO_WORK).status != CheckStatus.PENDING:
            return
        if not case.rtw_share_code or not case.rtw_share_code_dob:
            return
        orchestrator = Orchestrator(session, settings)
        provider = registry.rtw_for_case(case, settings)
        try:
            result = await provider.check_share_code(
                case, case.rtw_share_code, date.fromisoformat(case.rtw_share_code_dob)
            )
        except DriverInputError as exc:
            await orchestrator.record_rtw_input_error(case, exc.code, exc.message)
            return
        except ProviderTimeout:
            if attempt < RTW_MAX_ATTEMPTS:
                audit(session, case.id, f"provider:{provider.name}", "share_code.retry", attempt=attempt)
                await session.commit()
                await get_queue().enqueue(
                    "rtw_share_code_check", defer_by=2 ** (attempt - 1), case_id=case_id, attempt=attempt + 1
                )
                return
            result = provider.unavailable_result(
                case, f"The Home Office check didn't answer after {RTW_MAX_ATTEMPTS} tries. Run it by hand on gov.uk."
            )
        except ProviderError as exc:
            result = provider.unavailable_result(case, f"The share code check couldn't run: {exc}")
        await orchestrator.handle_rtw_result(case, result)


async def dvla_lookup(ctx: dict[str, Any], case_id: str, attempt: int = 1) -> None:
    settings = get_settings()
    async with session_factory()() as session:
        try:
            case = await load_case(session, uuid.UUID(case_id))
        except NotFound:
            return
        if case.status in (CaseStatus.PASSED, CaseStatus.FAILED, CaseStatus.MANUAL_REVIEW):
            return
        orchestrator = Orchestrator(session, settings)
        provider = registry.licence_for_case(case, settings)
        try:
            result = await provider.lookup(case)
        except ProviderTimeout:
            if attempt < DVLA_MAX_ATTEMPTS:
                audit(session, case.id, f"provider:{provider.name}", "dvla.lookup_retry", attempt=attempt)
                await session.commit()
                await get_queue().enqueue(
                    "dvla_lookup", defer_by=2 ** (attempt - 1), case_id=case_id, attempt=attempt + 1
                )
                return
            await orchestrator.apply_licence_result(case, None, f"The DVLA lookup timed out {DVLA_MAX_ATTEMPTS} times.")
            return
        except DriverInputError as exc:
            await orchestrator.record_licence_input_error(case, exc.code, exc.message)
            return
        except ProviderError as exc:
            await orchestrator.apply_licence_result(case, None, f"The licence check couldn't run: {exc}")
            return
        await orchestrator.apply_licence_result(case, result)


async def deliver_host_webhook(ctx: dict[str, Any], webhook_id: str) -> None:
    settings = get_settings()
    async with session_factory()() as session:
        webhook = await session.get(OutboundWebhook, uuid.UUID(webhook_id))
        if webhook is None or webhook.delivered_at is not None:
            return
        delivered = await notifier.deliver(webhook, settings)
        audit(
            session,
            webhook.case_id,
            "system",
            "webhook.delivered" if delivered else "webhook.attempt_failed",
            event=webhook.event,
            attempt=webhook.attempts,
            status_code=webhook.last_status_code,
        )
        await session.commit()
        attempts = webhook.attempts
    if not delivered and attempts < settings.webhook_max_attempts:
        await get_queue().enqueue("deliver_host_webhook", defer_by=2**attempts, webhook_id=webhook_id)


async def scan_rtw_expiring(ctx: dict[str, Any]) -> int:
    """Warn the host 28 days before time-limited permission ends. Test cases are skipped."""
    settings = get_settings()
    cutoff = date.today() + timedelta(days=settings.rtw_expiry_notice_days)
    queued = []
    async with session_factory()() as session:
        cases = (
            (
                await session.execute(
                    select(VerificationCase).where(
                        VerificationCase.status == CaseStatus.PASSED,
                        VerificationCase.is_test.is_(False),
                        VerificationCase.rtw_expires_at.is_not(None),
                        VerificationCase.rtw_expires_at <= cutoff,
                        VerificationCase.expiry_notified_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for case in cases:
            case.expiry_notified_at = utcnow()
            audit(session, case.id, "system", "rtw.expiry_notice", expires_at=case.rtw_expires_at.isoformat())
            webhook = notifier.queue_webhook(session, case, WebhookEvent.RTW_EXPIRING, settings)
            if webhook is not None:
                queued.append(webhook.id)
        await session.commit()
    for webhook_id in queued:
        await get_queue().enqueue("deliver_host_webhook", webhook_id=str(webhook_id))
    return len(cases)


async def purge_expired_data(ctx: dict[str, Any]) -> int:
    """Delete evidence past its retention date, and whole test cases after the test retention window."""
    settings = get_settings()
    store = get_evidence_store(settings)
    now = utcnow()
    async with session_factory()() as session:
        expired = (await session.execute(select(Evidence).where(Evidence.retain_until < now))).scalars().all()
        for item in expired:
            await store.delete(item.storage_key)
            await session.delete(item)
        test_cutoff = now - timedelta(hours=settings.test_case_retention_hours)
        result = await session.execute(
            delete(VerificationCase).where(
                VerificationCase.is_test.is_(True), VerificationCase.created_at < test_cutoff
            )
        )
        await session.commit()
    logger.info("Purged %s evidence files and %s test cases", len(expired), result.rowcount)
    return len(expired)


JOBS = {
    f.__name__: f
    for f in (
        deliver_mock_rtw_webhook,
        rtw_share_code_check,
        dvla_lookup,
        deliver_host_webhook,
        scan_rtw_expiring,
        purge_expired_data,
    )
}
