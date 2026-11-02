import hmac
import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_app_settings, require_host
from app.config import Settings
from app.db import get_session
from app.domain.enums import CheckStatus
from app.domain.models import Evidence, VerificationCase
from app.domain.schemas import (
    CheckOut,
    CreateVerificationRequest,
    DriverActionOut,
    EvidenceItem,
    EvidenceList,
    ReviewOut,
    ReviewRequest,
    SubmitLicenceRequest,
    SubmitShareCodeRequest,
    VerificationCreated,
    VerificationOut,
)
from app.errors import NotFound, Unauthorized
from app.security import sign
from app.services.evidence_store import get_evidence_store
from app.services.orchestrator import Orchestrator, load_case

router = APIRouter(prefix="/v1", tags=["verifications"], dependencies=[Depends(require_host)])
public_router = APIRouter(prefix="/v1", tags=["evidence"])


def to_out(case: VerificationCase) -> VerificationOut:
    review = None
    if case.review_decision:
        review = ReviewOut(
            decision=case.review_decision,
            note=case.review_note,
            reviewed_by=case.reviewed_by,
            reviewed_at=case.reviewed_at,
        )
    return VerificationOut(
        id=case.id,
        external_driver_id=case.driver.external_driver_id,
        route=case.route,
        status=case.status,
        is_test=case.is_test,
        mock_scenario=case.mock_scenario,
        driver_url=case.driver_url,
        rtw_expires_at=case.rtw_expires_at,
        licence_submitted=bool(case.driver.licence_number),
        dvla_consent=case.dvla_consent_at is not None,
        checks=[CheckOut.model_validate(c) for c in case.ordered_checks()],
        driver_action_required=[
            DriverActionOut(check=c.type, code=c.details["input_error"], message=c.reasons[0] if c.reasons else None)
            for c in case.ordered_checks()
            if c.status == CheckStatus.PENDING and c.details and "input_error" in c.details
        ],
        review=review,
        created_at=case.created_at,
        updated_at=case.updated_at,
        completed_at=case.completed_at,
    )


@router.post("/verifications", status_code=201, response_model=VerificationCreated)
async def create_verification(req: CreateVerificationRequest, session: AsyncSession = Depends(get_session)):
    case = await Orchestrator(session).create_case(req)
    return VerificationCreated(id=case.id, status=case.status, driver_url=case.driver_url, is_test=case.is_test)


@router.get("/verifications/{case_id}", response_model=VerificationOut)
async def get_verification(case_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return to_out(await load_case(session, case_id))


@router.post("/verifications/{case_id}/share-code", response_model=VerificationOut, status_code=202)
async def submit_share_code(
    case_id: uuid.UUID, req: SubmitShareCodeRequest, session: AsyncSession = Depends(get_session)
):
    """Start the Home Office check with the driver's share code. The result arrives by webhook."""
    case = await load_case(session, case_id, for_update=True)
    await Orchestrator(session).submit_share_code(case, req.share_code, req.date_of_birth)
    return to_out(case)


@router.post("/verifications/{case_id}/licence", response_model=VerificationOut)
async def submit_licence(case_id: uuid.UUID, req: SubmitLicenceRequest, session: AsyncSession = Depends(get_session)):
    case = await load_case(session, case_id, for_update=True)
    await Orchestrator(session).submit_licence(case, req.licence_number, req.check_code)
    return to_out(case)


@router.post("/verifications/{case_id}/review", response_model=VerificationOut)
async def review_verification(case_id: uuid.UUID, req: ReviewRequest, session: AsyncSession = Depends(get_session)):
    case = await load_case(session, case_id, for_update=True)
    await Orchestrator(session).record_review(case, req.decision, req.note, req.reviewed_by)
    return to_out(case)


def _evidence_signature(settings: Settings, evidence_id: uuid.UUID, expires: int) -> str:
    return sign(settings.evidence_url_secret, str(expires), str(evidence_id).encode())


def _evidence_url(settings: Settings, evidence_id: uuid.UUID, expires: int) -> str:
    signature = _evidence_signature(settings, evidence_id, expires)
    return f"{settings.public_base_url}/v1/evidence/{evidence_id}?expires={expires}&signature={signature}"


@router.get("/verifications/{case_id}/evidence", response_model=EvidenceList)
async def list_evidence(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
):
    await load_case(session, case_id)
    rows = (
        await session.execute(select(Evidence).where(Evidence.case_id == case_id).order_by(Evidence.created_at))
    ).scalars()
    expires = int(time.time()) + settings.evidence_url_ttl_seconds
    items = [
        EvidenceItem(
            id=e.id,
            kind=e.kind,
            content_type=e.content_type,
            size_bytes=e.size_bytes,
            url=_evidence_url(settings, e.id, expires),
            url_expires_at=datetime.fromtimestamp(expires, UTC),
        )
        for e in rows
    ]
    return EvidenceList(items=items)


@public_router.get("/evidence/{evidence_id}")
async def download_evidence(
    evidence_id: uuid.UUID,
    expires: str,
    signature: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
):
    """Short-lived signed link, so the host can hand it to a browser without the API key."""
    valid = (
        expires.isdigit()
        and int(expires) >= time.time()
        and hmac.compare_digest(_evidence_signature(settings, evidence_id, int(expires)), signature)
    )
    if not valid:
        raise Unauthorized("This evidence link is invalid or has expired.")
    evidence = await session.get(Evidence, evidence_id)
    if evidence is None:
        raise NotFound("Evidence not found. It may have been deleted under the retention policy.")
    data = await get_evidence_store(settings).get(evidence.storage_key)
    return Response(
        content=data,
        media_type=evidence.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{evidence.kind}-{evidence.case_id}.pdf"',
            "Cache-Control": "no-store",
        },
    )
