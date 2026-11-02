import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app import db
from app.db import utcnow
from app.domain.enums import CaseStatus, CheckStatus, CheckType
from app.domain.models import Check, Driver, Evidence, OutboundWebhook, VerificationCase
from app.workers.jobs import purge_expired_data, scan_rtw_expiring
from tests.conftest import DEMO_CALLBACK, drain


async def add_passed_case(is_test: bool, expires_in_days: int | None) -> uuid.UUID:
    async with db.session_factory()() as session:
        driver = Driver(
            external_driver_id=f"drv-{uuid.uuid4().hex[:6]}", first_name="Ana", last_name="Silva", dob="1990-01-01"
        )
        case = VerificationCase(
            id=uuid.uuid4(),
            driver=driver,
            route="share_code",
            status=CaseStatus.PASSED,
            is_test=is_test,
            callback_url=DEMO_CALLBACK,
            rtw_expires_at=date.today() + timedelta(days=expires_in_days) if expires_in_days is not None else None,
            checks=[Check(type=t, status=CheckStatus.PASS, reasons=[]) for t in CheckType],
        )
        session.add(case)
        await session.commit()
        return case.id


async def test_expiry_notice_goes_out_once_and_skips_test_cases(app):
    due = await add_passed_case(is_test=False, expires_in_days=20)
    later = await add_passed_case(is_test=False, expires_in_days=60)
    test_case = await add_passed_case(is_test=True, expires_in_days=5)

    assert await scan_rtw_expiring({}) == 1
    await drain(app)
    assert await scan_rtw_expiring({}) == 0

    async with db.session_factory()() as session:
        hooks = (await session.execute(select(OutboundWebhook))).scalars().all()
    assert [(h.case_id, h.event) for h in hooks] == [(due, "rtw.expiring")]
    assert hooks[0].delivered_at is not None
    assert later not in {h.case_id for h in hooks} and test_case not in {h.case_id for h in hooks}


async def test_purge_removes_expired_evidence_and_old_test_cases(app, settings):
    old_test_case = await add_passed_case(is_test=True, expires_in_days=None)
    live_case = await add_passed_case(is_test=False, expires_in_days=None)
    async with db.session_factory()() as session:
        case = await session.get(VerificationCase, old_test_case)
        case.created_at = utcnow() - timedelta(hours=settings.test_case_retention_hours + 1)
        session.add(
            Evidence(
                case_id=live_case,
                kind="rtw_profile",
                content_type="application/pdf",
                storage_key=f"{live_case}/gone",
                size_bytes=1,
                retain_until=utcnow() - timedelta(minutes=1),
            )
        )
        session.add(
            Evidence(
                case_id=live_case,
                kind="rtw_profile",
                content_type="application/pdf",
                storage_key=f"{live_case}/kept",
                size_bytes=1,
                retain_until=None,
            )
        )
        await session.commit()

    assert await purge_expired_data({}) == 1
    async with db.session_factory()() as session:
        assert await session.get(VerificationCase, old_test_case) is None
        assert await session.get(VerificationCase, live_case) is not None
        keys = (await session.execute(select(Evidence.storage_key))).scalars().all()
    assert keys == [f"{live_case}/kept"]
