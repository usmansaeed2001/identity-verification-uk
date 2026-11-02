"""Simulated DVLA licence data provider (stands in for an ADD API intermediary)."""

import asyncio
import random
import uuid
from datetime import date, timedelta

from app.config import Settings
from app.domain.enums import CheckStatus
from app.domain.models import VerificationCase
from app.providers.base import CheckOutcome, LicenceResult, Person, ProviderTimeout

HGV_CATEGORIES = {"C", "CE"}


class MockDvlaProvider:
    name = "mock_dvla"
    requires_check_code = False

    def __init__(self, settings: Settings):
        self.settings = settings

    async def lookup(self, case: VerificationCase) -> LicenceResult:
        await asyncio.sleep(random.uniform(self.settings.mock_delay_min_seconds, self.settings.mock_delay_max_seconds))
        scenario = case.mock_scenario
        if scenario == "dvla_timeout":
            raise ProviderTimeout("Mock DVLA lookup timed out")

        today = date.today()
        driver = case.driver
        categories = ["B", "C1"] if scenario == "no_hgv_entitlement" else ["B", "C1", "C", "CE"]
        points = 3
        licence_valid_to = today + timedelta(days=1800)

        licence = CheckOutcome(
            CheckStatus.PASS,
            details={
                "categories": categories,
                "points": points,
                "disqualified": False,
                "licence_valid_to": licence_valid_to.isoformat(),
                "person": Person(driver.full_name, driver.date_of_birth).to_dict(),
            },
        )
        if not HGV_CATEGORIES & set(categories):
            licence.status = CheckStatus.FAIL
            licence.reasons = ["The licence has no entitlement to drive category C or C+E."]

        cpc_expires = today - timedelta(days=30) if scenario == "cpc_expired" else today + timedelta(days=900)
        cpc = CheckOutcome(CheckStatus.PASS, details={"dqc_expires_at": cpc_expires.isoformat()})
        if cpc_expires < today:
            cpc.status = CheckStatus.FAIL
            cpc.reasons = [f"The Driver CPC expired on {cpc_expires:%d %B %Y}."]

        return LicenceResult(
            provider_ref=f"dvla_{uuid.uuid4().hex[:16]}",
            licence=licence,
            cpc=cpc,
            person=Person(driver.full_name, driver.date_of_birth),
            categories=categories,
            points=points,
        )
