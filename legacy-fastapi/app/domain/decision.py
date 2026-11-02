"""Turns individual check results into one case outcome."""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.domain.enums import CaseStatus, CheckStatus


class CheckLike(Protocol):
    type: str
    status: str
    reasons: list[str]


@dataclass(frozen=True)
class Decision:
    status: CaseStatus
    reasons: list[str] = field(default_factory=list)


def decide(checks: Iterable[CheckLike]) -> Decision:
    """Any failure fails the case, even while other checks are still running.

    Otherwise the case waits for every check; then anything unclear goes to a
    person, and the case passes only when every check passed.
    """
    checks = list(checks)
    failed = [c for c in checks if c.status == CheckStatus.FAIL]
    if failed:
        return Decision(CaseStatus.FAILED, [r for c in failed for r in c.reasons])
    if any(c.status == CheckStatus.PENDING for c in checks):
        return Decision(CaseStatus.IN_PROGRESS)
    unclear = [c for c in checks if c.status == CheckStatus.UNCLEAR]
    if unclear:
        return Decision(CaseStatus.MANUAL_REVIEW, [r for c in unclear for r in c.reasons])
    return Decision(CaseStatus.PASSED)


@dataclass(frozen=True)
class IdentitySource:
    label: str  # e.g. "Home Office record"
    full_name: str
    dob: date


def _name_tokens(name: str) -> set[str]:
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = re.sub(r"['’.]", "", ascii_only.casefold())
    return {t for t in re.split(r"[\s\-]+", cleaned) if t}


def compare_identity(
    first_name: str, last_name: str, dob: date, sources: Iterable[IdentitySource]
) -> tuple[CheckStatus, list[str]]:
    """Compare the details the host gave us with each source document.

    Reasons never contain the names themselves; the host already has them.
    """
    expected = _name_tokens(f"{first_name} {last_name}")
    surname = _name_tokens(last_name)
    status = CheckStatus.PASS
    reasons: list[str] = []
    sources = list(sources)
    if not sources:
        return CheckStatus.UNCLEAR, ["No document details were available to compare."]

    for source in sources:
        if source.dob != dob:
            status = CheckStatus.FAIL
            reasons.append(f"Date of birth on the {source.label} doesn't match.")
        found = _name_tokens(source.full_name)
        if found == expected:
            continue
        shares_surname = bool(surname & found)
        if shares_surname and (expected <= found or found <= expected):
            if status != CheckStatus.FAIL:
                status = CheckStatus.UNCLEAR
            reasons.append(f"Name on the {source.label} has extra or missing names, such as a middle name.")
        else:
            status = CheckStatus.FAIL
            reasons.append(f"Name on the {source.label} doesn't match.")
    return status, reasons
