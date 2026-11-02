"""Provider result types. Real adapters and stubs all normalise into these."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from onboarding.enums import CheckStatus


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
    def from_dict(cls, data: dict[str, str]) -> "Person":
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
class RtwResult:
    provider_ref: str
    right_to_work: CheckOutcome
    person_on_rtw: Person | None
    rtw_expires_at: date | None
    evidence: list[EvidenceFile] = field(default_factory=list)


@dataclass
class LicenceResult:
    provider_ref: str
    licence: CheckOutcome
    cpc: CheckOutcome
    categories: list[str]
    points: int
    evidence: list[EvidenceFile] = field(default_factory=list)


@dataclass
class IdentityResult:
    identity_document: CheckOutcome
    liveness: CheckOutcome
    face_match: CheckOutcome
    person_on_document: Person | None = None


class IdentityProvider(Protocol):
    name: str

    def verify(self, document_type: str, document_images: list[bytes], selfie_frames: list[bytes]) -> IdentityResult:
        """Check the ID is genuine, the selfie is a live person, and the two faces match."""
        ...
