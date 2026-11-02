from enum import StrEnum


class Route(StrEnum):
    SHARE_CODE = "share_code"
    BRITISH_IRISH = "british_irish"


class Mode(StrEnum):
    LIVE = "live"
    MOCK = "mock"


class CaseStatus(StrEnum):
    CREATED = "CREATED"
    AWAITING_DRIVER = "AWAITING_DRIVER"
    IN_PROGRESS = "IN_PROGRESS"
    PASSED = "PASSED"
    FAILED = "FAILED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


FINISHED_STATUSES = frozenset({CaseStatus.PASSED, CaseStatus.FAILED})
DECIDED_STATUSES = FINISHED_STATUSES | {CaseStatus.MANUAL_REVIEW}


class CheckType(StrEnum):
    RIGHT_TO_WORK = "right_to_work"
    IDENTITY_DOCUMENT = "identity_document"
    LIVENESS = "liveness"
    NAME_DOB_MATCH = "name_dob_match"
    DVLA_LICENCE = "dvla_licence"
    DRIVER_CPC = "driver_cpc"


class CheckStatus(StrEnum):
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
    UNCLEAR = "unclear"
    SKIPPED = "skipped"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class WebhookEvent(StrEnum):
    COMPLETED = "verification.completed"
    REQUIRES_REVIEW = "verification.requires_review"
    DRIVER_ACTION_REQUIRED = "verification.driver_action_required"
    RTW_EXPIRING = "rtw.expiring"


class EvidenceKind(StrEnum):
    RTW_PROFILE = "rtw_profile"
    IDSP_REPORT = "idsp_report"
    HOME_OFFICE_PHOTO = "home_office_photo"
    DVLA_SUMMARY = "dvla_summary"
