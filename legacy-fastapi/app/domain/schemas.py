import uuid
from datetime import date, datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import Mode, ReviewDecision, Route
from app.domain.validation import validate_dvla_check_code, validate_licence_number, validate_share_code


class CreateVerificationRequest(BaseModel):
    external_driver_id: str = Field(min_length=1, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    dob: date
    route: Route
    licence_number: str | None = None
    dvla_consent: bool = False
    callback_url: AnyHttpUrl | None = None
    mode: Mode = Mode.LIVE
    mock_scenario: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("dob")
    @classmethod
    def _adult(cls, value: date) -> date:
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18:
            raise ValueError("HGV drivers must be at least 18")
        if age > 100:
            raise ValueError("date of birth looks wrong")
        return value

    @field_validator("licence_number")
    @classmethod
    def _licence(cls, value: str | None) -> str | None:
        return validate_licence_number(value) if value else None


class SubmitShareCodeRequest(BaseModel):
    share_code: str
    date_of_birth: date

    @field_validator("share_code")
    @classmethod
    def _share_code(cls, value: str) -> str:
        # The W prefix is enforced by the orchestrator, which knows whether we're on a sandbox key.
        return validate_share_code(value, require_w_prefix=False)


class SubmitLicenceRequest(BaseModel):
    licence_number: str
    dvla_consent: bool
    # Needed when the licence provider uses DVLA check codes (gov.uk/view-driving-licence).
    check_code: str | None = None

    @field_validator("licence_number")
    @classmethod
    def _licence(cls, value: str) -> str:
        return validate_licence_number(value)

    @field_validator("check_code")
    @classmethod
    def _check_code(cls, value: str | None) -> str | None:
        return validate_dvla_check_code(value) if value else None

    @field_validator("dvla_consent")
    @classmethod
    def _consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("the driver must agree to the DVLA licence check")
        return value


class ReviewRequest(BaseModel):
    decision: ReviewDecision
    note: str = Field(min_length=3, max_length=2000)
    reviewed_by: str = Field(min_length=1, max_length=128)


class VerificationCreated(BaseModel):
    id: uuid.UUID
    status: str
    driver_url: str | None
    is_test: bool


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    status: str
    reasons: list[str]
    provider: str | None
    completed_at: datetime | None


class DriverActionOut(BaseModel):
    check: str
    code: str
    message: str | None


class ReviewOut(BaseModel):
    decision: str
    note: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None


class VerificationOut(BaseModel):
    id: uuid.UUID
    external_driver_id: str
    route: str
    status: str
    is_test: bool
    mock_scenario: str | None
    driver_url: str | None
    rtw_expires_at: date | None
    licence_submitted: bool
    dvla_consent: bool
    checks: list[CheckOut]
    driver_action_required: list[DriverActionOut]
    review: ReviewOut | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class EvidenceItem(BaseModel):
    id: uuid.UUID
    kind: str
    content_type: str
    size_bytes: int
    url: str
    url_expires_at: datetime


class EvidenceList(BaseModel):
    items: list[EvidenceItem]
