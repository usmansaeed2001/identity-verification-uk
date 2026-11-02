import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.domain.models import InboundEvent, VerificationCase
from app.errors import NotFound, Unauthorized
from app.providers import registry
from app.services.orchestrator import Orchestrator, load_case

logger = logging.getLogger(__name__)

router = APIRouter(tags=["provider webhooks"])


@router.post("/webhooks/{provider_name}")
async def receive_provider_webhook(provider_name: str, request: Request, session: AsyncSession = Depends(get_session)):
    settings = request.app.state.settings
    provider = registry.rtw_by_webhook_name(provider_name, settings)
    if provider is None:
        raise NotFound("Unknown provider.")
    body = await request.body()
    if not provider.verify_webhook(request.headers, body):
        raise Unauthorized("Invalid webhook signature.")
    result = await provider.parse_webhook(body)

    case_id = (
        await session.execute(
            select(VerificationCase.id).where(
                VerificationCase.rtw_provider == provider.name,
                VerificationCase.rtw_session_ref == result.session_ref,
            )
        )
    ).scalar_one_or_none()
    if case_id is None:
        raise NotFound("No verification matches this session.")

    session.add(InboundEvent(provider=provider.name, event_id=result.event_id))
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        logger.info("Duplicate %s webhook %s ignored", provider.name, result.event_id)
        return {"status": "duplicate"}

    case = await load_case(session, case_id, for_update=True)
    await Orchestrator(session).handle_rtw_result(case, result)
    return {"status": "accepted"}
