"""Signed webhooks to the host platform, recorded so they can be retried and audited."""

import json
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import utcnow
from app.domain.enums import CheckStatus, CheckType, WebhookEvent
from app.domain.models import OutboundWebhook, VerificationCase
from app.http import get_http_client
from app.security import signed_headers
from app.services.audit import audit

logger = logging.getLogger(__name__)

SIGNATURE_PREFIX = "X-Webhook"


def build_payload(case: VerificationCase, event: WebhookEvent, webhook_id: uuid.UUID) -> dict[str, Any]:
    checks = case.ordered_checks()
    payload: dict[str, Any] = {
        "event": str(event),
        "webhook_id": str(webhook_id),
        "verification_id": str(case.id),
        "external_driver_id": case.driver.external_driver_id,
        "status": case.status,
        "is_test": case.is_test,
        "route": case.route,
        "checks": {c.type: c.status for c in checks},
        "reasons": [r for c in checks if c.status in (CheckStatus.FAIL, CheckStatus.UNCLEAR) for r in c.reasons],
        "rtw_expires_at": case.rtw_expires_at.isoformat() if case.rtw_expires_at else None,
        "occurred_at": utcnow().isoformat(),
    }
    # Checks waiting for the driver to re-enter something (a new share code or DVLA check code).
    action_required = [
        {"check": c.type, "code": c.details["input_error"], "message": c.reasons[0] if c.reasons else None}
        for c in checks
        if c.status == CheckStatus.PENDING and c.details and "input_error" in c.details
    ]
    if action_required:
        payload["driver_action_required"] = action_required
    licence = case.check(CheckType.DVLA_LICENCE)
    if licence.details:
        payload["licence"] = {
            "categories": licence.details.get("categories", []),
            "points": licence.details.get("points"),
        }
    if case.review_decision:
        payload["review"] = {
            "decision": case.review_decision,
            "note": case.review_note,
            "reviewed_by": case.reviewed_by,
        }
    return payload


def queue_webhook(
    session: AsyncSession, case: VerificationCase, event: WebhookEvent, settings: Settings
) -> OutboundWebhook | None:
    """Record a webhook for delivery. The caller commits, then enqueues deliver_host_webhook."""
    url = case.callback_url or settings.default_callback_url
    if not url:
        audit(session, case.id, "system", "webhook.skipped", event=str(event), reason="no callback URL")
        return None
    webhook_id = uuid.uuid4()
    webhook = OutboundWebhook(
        id=webhook_id, case_id=case.id, event=str(event), url=url, payload=build_payload(case, event, webhook_id)
    )
    session.add(webhook)
    return webhook


async def deliver(webhook: OutboundWebhook, settings: Settings) -> bool:
    """One delivery attempt. Updates the webhook row; the caller commits."""
    body = json.dumps(webhook.payload, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json", "X-Webhook-Id": str(webhook.id)}
    headers.update(signed_headers(settings.webhook_signing_secret, body, SIGNATURE_PREFIX))
    webhook.attempts += 1
    try:
        response = await get_http_client().post(webhook.url, content=body, headers=headers)
    except Exception as exc:  # network errors are retried
        webhook.last_error = f"{type(exc).__name__}: {exc}"[:500]
        webhook.last_status_code = None
        logger.warning("Webhook %s attempt %s failed: %s", webhook.id, webhook.attempts, webhook.last_error)
        return False
    webhook.last_status_code = response.status_code
    if response.is_success:
        webhook.delivered_at = utcnow()
        webhook.last_error = None
        return True
    webhook.last_error = f"HTTP {response.status_code}"
    return False
