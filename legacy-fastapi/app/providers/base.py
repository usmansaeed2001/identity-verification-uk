"""Provider interfaces. Real vendor adapters and the mocks both normalise into these types."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from app.domain.enums import CheckStatus
from app.domain.models import VerificationCase


class ProviderTimeout(Exception):
    """A temporary failure: the same request can be retried."""


class ProviderError(Exception):
    """The provider refused for a reason retrying won't fix (bad key, quota used up)."""


class DriverInputError(Exception):
    """The provider couldn't use what the driver entered; the driver has to enter it again."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Person:
    full_name: str
    dob: date

    def to_dict(self) -> dict[str, str]:
        return {"full_name": self.full_name, "dob": self.dob.isoformat()}

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> "Person":
        return cls(full_name=data["full_name"], dob=date.fromisoformat(data["dob"]))


@dataclass
class CheckOutcome:
    status: CheckStatus
    reasons: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceFile:
    kind: str
    content_type: str
    data: bytes


@dataclass
class RtwSession:
    session_ref: str
    driver_url: str


@dataclass
class RtwResult:
    """What the RTW vendor tells us once the driver finishes the hosted flow."""

    event_id: str
    session_ref: str
    provider_ref: str
    right_to_work: CheckOutcome
    identity_document: CheckOutcome
    liveness: CheckOutcome
    person_on_rtw: Person | None
    person_on_document: Person | None
    rtw_expires_at: date | None
    evidence: list[EvidenceFile] = field(default_factory=list)


@dataclass
class LicenceResult:
    provider_ref: str
    licence: CheckOutcome
    cpc: CheckOutcome
    person: Person | None
    categories: list[str]
    points: int
    evidence: list[EvidenceFile] = field(default_factory=list)


class RtwProvider(Protocol):
    """A hosted vendor: the driver completes its flow and it reports back by webhook."""

    name: str

    async def create_session(self, case: VerificationCase) -> RtwSession: ...

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool: ...

    async def parse_webhook(self, body: bytes) -> RtwResult: ...


class ShareCodeProvider(Protocol):
    """A provider we call directly with the share code the driver gave us."""

    name: str

    async def create_session(self, case: VerificationCase) -> RtwSession: ...

    async def check_share_code(self, case: VerificationCase, share_code: str, dob: date) -> RtwResult:
        """Raises DriverInputError, ProviderTimeout or ProviderError."""
        ...

    def unavailable_result(self, case: VerificationCase, reason: str) -> RtwResult: ...


class LicenceProvider(Protocol):
    name: str
    # True when the driver must give a DVLA check code (case.dvla_check_code) for each check.
    requires_check_code: bool

    async def lookup(self, case: VerificationCase) -> LicenceResult:
        """Look up case.driver.licence_number. Raises ProviderTimeout when DVLA doesn't answer."""
        ...
