import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuditEvent


def audit(session: AsyncSession, case_id: uuid.UUID, actor: str, action: str, **detail: Any) -> None:
    """Add an audit event to the session. Never pass raw share codes or licence numbers."""
    session.add(AuditEvent(case_id=case_id, actor=actor, action=action, detail=detail))
