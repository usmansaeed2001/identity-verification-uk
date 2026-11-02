import itertools
from dataclasses import dataclass, field
from datetime import date

import pytest

from onboarding.decision import SIMULATED_GATE_REASON, IdentitySource, compare_identity, decide
from onboarding.enums import ApplicationStatus, CheckStatus, CheckType


@dataclass
class FakeCheck:
    type: str
    status: str
    reasons: list[str] = field(default_factory=list)
    details: dict | None = None


def checks(**statuses: CheckStatus) -> list[FakeCheck]:
    return [
        FakeCheck(
            t,
            statuses.get(t.value, CheckStatus.PASS),
            [f"{t.value} {statuses[t.value]}"] if t.value in statuses else [],
        )
        for t in CheckType
    ]


def test_all_pass():
    assert decide(checks()).status == ApplicationStatus.PASSED


@pytest.mark.parametrize("status", [CheckStatus.PENDING, CheckStatus.RUNNING])
def test_unfinished_checks_keep_it_in_progress(status):
    assert decide(checks(driver_cpc=status)).status == ApplicationStatus.IN_PROGRESS


def test_failure_wins_even_while_other_checks_are_pending():
    decision = decide(checks(right_to_work=CheckStatus.FAIL, dvla_licence=CheckStatus.PENDING))
    assert decision.status == ApplicationStatus.FAILED
    assert decision.reasons == ["right_to_work fail"]


def test_unclear_goes_to_manual_review_with_reasons():
    decision = decide(checks(liveness=CheckStatus.UNCLEAR))
    assert decision.status == ApplicationStatus.MANUAL_REVIEW
    assert decision.reasons == ["liveness unclear"]


def test_a_simulated_pass_never_approves_on_its_own():
    all_pass = checks()
    all_pass[1].details = {"simulated": True}
    decision = decide(all_pass)
    assert decision.status == ApplicationStatus.MANUAL_REVIEW
    assert decision.reasons == [SIMULATED_GATE_REASON]


def test_a_failure_still_fails_with_simulated_checks():
    mixed = checks(dvla_licence=CheckStatus.FAIL)
    mixed[1].details = {"simulated": True}
    assert decide(mixed).status == ApplicationStatus.FAILED


@pytest.mark.parametrize(
    "combo", list(itertools.product([CheckStatus.PASS, CheckStatus.FAIL, CheckStatus.UNCLEAR], repeat=len(CheckType)))
)
def test_every_combination_follows_the_rules(combo):
    result = decide([FakeCheck(t, s) for t, s in zip(CheckType, combo, strict=True)]).status
    if CheckStatus.FAIL in combo:
        assert result == ApplicationStatus.FAILED
    elif CheckStatus.UNCLEAR in combo:
        assert result == ApplicationStatus.MANUAL_REVIEW
    else:
        assert result == ApplicationStatus.PASSED


DOB = date(1987, 3, 14)


def test_identity_matches_ignoring_case_and_accents():
    status, reasons = compare_identity("Zoë", "O'Neill", DOB, [IdentitySource("DVLA record", "ZOE ONEILL", DOB)])
    assert status == CheckStatus.PASS and reasons == []


def test_middle_name_needs_a_person():
    status, reasons = compare_identity(
        "Tomasz", "Nowak", DOB, [IdentitySource("right to work record", "Tomasz Lee Nowak", DOB)]
    )
    assert status == CheckStatus.UNCLEAR
    assert "middle name" in reasons[0]
    assert "Tomasz" not in reasons[0]


def test_different_person_or_dob_fails():
    status, _ = compare_identity("Tomasz", "Nowak", DOB, [IdentitySource("identity document", "Adam Smith", DOB)])
    assert status == CheckStatus.FAIL
    status, reasons = compare_identity(
        "Tomasz", "Nowak", DOB, [IdentitySource("DVLA record", "Tomasz Nowak", date(1987, 3, 15))]
    )
    assert status == CheckStatus.FAIL
    assert reasons == ["Date of birth on the DVLA record doesn't match."]


def test_no_sources_is_unclear():
    assert compare_identity("A", "B", DOB, [])[0] == CheckStatus.UNCLEAR
