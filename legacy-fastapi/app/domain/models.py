import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, EncryptedJSON, EncryptedString, UTCDateTime, utcnow
from app.domain.enums import CaseStatus, CheckStatus, CheckType

# SQLite only autoincrements INTEGER primary keys.
AutoIncrementId = BigInteger().with_variant(Integer, "sqlite")

CHECK_ORDER = [
    CheckType.RIGHT_TO_WORK,
    CheckType.IDENTITY_DOCUMENT,
    CheckType.LIVENESS,
    CheckType.NAME_DOB_MATCH,
    CheckType.DVLA_LICENCE,
    CheckType.DRIVER_CPC,
]


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    external_driver_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(EncryptedString)
    last_name: Mapped[str] = mapped_column(EncryptedString)
    dob: Mapped[str] = mapped_column(EncryptedString)  # ISO date, encrypted
    licence_number: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    @property
    def date_of_birth(self) -> date:
        return date.fromisoformat(self.dob)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class VerificationCase(Base):
    __tablename__ = "verification_cases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"), index=True)
    route: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True, default=CaseStatus.CREATED)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    mock_scenario: Mapped[str | None] = mapped_column(String(40), nullable=True)

    rtw_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rtw_session_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    licence_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    driver_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    callback_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Single-use codes from the driver, encrypted and cleared once a check has used them.
    rtw_share_code: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    rtw_share_code_dob: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    dvla_check_code: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)

    dvla_consent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    dvla_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    rtw_expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    review_decision: Mapped[str | None] = mapped_column(String(10), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    driver: Mapped[Driver] = relationship(lazy="selectin")
    checks: Mapped[list["Check"]] = relationship(back_populates="case", lazy="selectin", cascade="all, delete-orphan")

    def check(self, check_type: CheckType) -> "Check":
        for check in self.checks:
            if check.type == check_type:
                return check
        raise KeyError(check_type)

    def ordered_checks(self) -> list["Check"]:
        return sorted(self.checks, key=lambda c: CHECK_ORDER.index(CheckType(c.type)))


class Check(Base):
    __tablename__ = "checks"
    __table_args__ = (UniqueConstraint("case_id", "type", name="uq_checks_case_type"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("verification_cases.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(10), default=CheckStatus.PENDING)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Normalised provider data (names, dates, categories). Encrypted: it holds PII.
    details: Mapped[dict[str, Any] | None] = mapped_column(EncryptedJSON, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    case: Mapped[VerificationCase] = relationship(back_populates="checks")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("verification_cases.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    content_type: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    # None means "keep until the host tells us employment has ended".
    retain_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditEvent(Base):
    """Append-only record of everything that happened to a case."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(AutoIncrementId, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("verification_cases.id", ondelete="CASCADE"), index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class InboundEvent(Base):
    """Provider webhook ids already processed, so replays are ignored."""

    __tablename__ = "inbound_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_inbound_provider_event"),)

    id: Mapped[int] = mapped_column(AutoIncrementId, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(40))
    event_id: Mapped[str] = mapped_column(String(128))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OutboundWebhook(Base):
    __tablename__ = "outbound_webhooks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("verification_cases.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(40))
    url: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
