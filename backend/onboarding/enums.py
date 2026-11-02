from django.db import models


class Route(models.TextChoices):
    SHARE_CODE = "share_code", "Share code (not British or Irish)"
    BRITISH_IRISH = "british_irish", "British or Irish citizen"


class ApplicationStatus(models.TextChoices):
    DRAFT = "DRAFT", "In progress"
    IN_PROGRESS = "IN_PROGRESS", "Checks running"
    ACTION_REQUIRED = "ACTION_REQUIRED", "Action needed"
    MANUAL_REVIEW = "MANUAL_REVIEW", "In review"
    PASSED = "PASSED", "Approved"
    FAILED = "FAILED", "Not approved"


EDITABLE_STATUSES = frozenset({ApplicationStatus.DRAFT, ApplicationStatus.ACTION_REQUIRED})


class Step(models.TextChoices):
    PROFILE = "profile", "About you"
    CONSENT = "consent", "Consent"
    DOCUMENT = "document", "Photo ID"
    SELFIE = "selfie", "Face scan"
    RIGHT_TO_WORK = "right_to_work", "Right to work"
    LICENCE = "licence", "Driving licence"


class DocumentType(models.TextChoices):
    PASSPORT = "passport", "Passport"
    UK_LICENCE = "uk_licence", "UK photocard driving licence"
    ID_CARD = "id_card", "EU/EEA national ID card"


DOCUMENTS_WITH_BACK = frozenset({DocumentType.UK_LICENCE, DocumentType.ID_CARD})


class CheckType(models.TextChoices):
    RIGHT_TO_WORK = "right_to_work", "Right to work"
    IDENTITY_DOCUMENT = "identity_document", "Photo ID"
    LIVENESS = "liveness", "Liveness"
    FACE_MATCH = "face_match", "Face match"
    NAME_DOB_MATCH = "name_dob_match", "Name and date of birth"
    DVLA_LICENCE = "dvla_licence", "DVLA licence"
    DRIVER_CPC = "driver_cpc", "Driver CPC"


CHECK_ORDER = list(CheckType)


class CheckStatus(models.TextChoices):
    PENDING = "pending"
    RUNNING = "running"
    PASS = "pass"
    FAIL = "fail"
    UNCLEAR = "unclear"
    SKIPPED = "skipped"


DONE_CHECK_STATUSES = frozenset({CheckStatus.PASS, CheckStatus.FAIL, CheckStatus.UNCLEAR, CheckStatus.SKIPPED})


class EvidenceKind(models.TextChoices):
    ID_FRONT = "id_front", "Photo ID (front)"
    ID_BACK = "id_back", "Photo ID (back)"
    SELFIE = "selfie", "Selfie"
    DQC_CARD = "dqc_card", "Driver qualification card"
    RTW_PROFILE_PDF = "rtw_profile_pdf", "Home Office right to work profile"
    HOME_OFFICE_PHOTO = "home_office_photo", "Home Office photo"
    DVLA_SUMMARY_PDF = "dvla_summary_pdf", "DVLA licence summary"


class ReviewDecision(models.TextChoices):
    APPROVE = "approve"
    REJECT = "reject"
