"""Named outcomes for the mock providers. Driver input is ignored in mock mode."""

from dataclasses import dataclass

from app.domain.enums import CaseStatus, Route
from app.errors import InvalidRequest

BOTH_ROUTES = frozenset(Route)


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    description: str
    expected: CaseStatus
    routes: frozenset[Route] = BOTH_ROUTES


SCENARIOS: dict[str, Scenario] = {
    s.key: s
    for s in [
        Scenario("all_pass", "All checks pass", "Every check passes.", CaseStatus.PASSED),
        Scenario(
            "rtw_expired",
            "Share code permission expired",
            "The Home Office record shows permission to work has ended.",
            CaseStatus.FAILED,
            frozenset({Route.SHARE_CODE}),
        ),
        Scenario(
            "face_mismatch",
            "Face match below threshold",
            "Liveness passes but the selfie only weakly matches the document photo.",
            CaseStatus.MANUAL_REVIEW,
        ),
        Scenario(
            "name_mismatch",
            "Name mismatch (middle name)",
            "The documents include a middle name the host didn't send.",
            CaseStatus.MANUAL_REVIEW,
        ),
        Scenario(
            "no_hgv_entitlement",
            "No C/C+E entitlement",
            "The licence is valid for cars and C1 only.",
            CaseStatus.FAILED,
        ),
        Scenario("cpc_expired", "CPC expired", "The Driver CPC ran out last month.", CaseStatus.FAILED),
        Scenario(
            "dvla_timeout",
            "DVLA lookup timeout",
            "DVLA doesn't answer, even after retries.",
            CaseStatus.MANUAL_REVIEW,
        ),
    ]
}

DEFAULT_SCENARIO = "all_pass"


def get_scenario(key: str, route: Route) -> Scenario:
    scenario = SCENARIOS.get(key)
    if scenario is None:
        raise InvalidRequest(f"Unknown mock_scenario '{key}'. Choose one of: {', '.join(SCENARIOS)}.")
    if route not in scenario.routes:
        raise InvalidRequest(f"The '{key}' scenario doesn't apply to the {route} route.")
    return scenario
