import uuid
from datetime import date

from django.conf import settings
from django.db import models

from common.fields import EncryptedJSONField, EncryptedTextField
from onboarding.enums import (
    CHECK_ORDER,
    ApplicationStatus,
    CheckStatus,
    CheckType,
    DocumentType,
    EvidenceKind,
    ReviewDecision,
    Route,
)


class Application(models.Model):
    """One driver's onboarding: their details, the codes they gave us, and the review outcome."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="application")
    status = models.CharField(max_length=20, choices=ApplicationStatus.choices, default=ApplicationStatus.DRAFT)
    route = models.CharField(max_length=20, choices=Route.choices, blank=True)

    first_name = EncryptedTextField(null=True, blank=True)
    last_name = EncryptedTextField(null=True, blank=True)
    dob = EncryptedTextField(null=True, blank=True)  # ISO date
    phone = EncryptedTextField(null=True, blank=True)

    consent_at = models.DateTimeField(null=True, blank=True)
    dvla_consent_at = models.DateTimeField(null=True, blank=True)
    document_type = models.CharField(max_length=20, choices=DocumentType.choices, blank=True)
    licence_number = EncryptedTextField(null=True, blank=True)

    # Single-use codes, encrypted and cleared as soon as a check has used them.
    share_code = EncryptedTextField(null=True, blank=True)
    share_code_dob = EncryptedTextField(null=True, blank=True)
    dvla_check_code = EncryptedTextField(null=True, blank=True)

    rtw_expires_at = models.DateField(null=True, blank=True)
    # Steps a reviewer sent back to the driver, with their message.
    reopened_steps = models.JSONField(default=list, blank=True)
    action_message = models.TextField(blank=True)
    # Set when a sandbox key ran the checks: never treat as a real driver.
    is_test = models.BooleanField(default=False)

    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    review_decision = models.CharField(max_length=10, choices=ReviewDecision.choices, blank=True)
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Application {self.id} ({self.status})"

    @property
    def date_of_birth(self) -> date | None:
        return date.fromisoformat(self.dob) if self.dob else None

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p)

    def get_check(self, check_type: CheckType) -> "Check":
        check, _ = Check.objects.get_or_create(application=self, type=check_type)
        return check

    def ordered_checks(self) -> list["Check"]:
        return sorted(self.checks.all(), key=lambda c: CHECK_ORDER.index(CheckType(c.type)))


class Check(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="checks")
    type = models.CharField(max_length=30, choices=CheckType.choices)
    status = models.CharField(max_length=10, choices=CheckStatus.choices, default=CheckStatus.PENDING)
    reasons = models.JSONField(default=list, blank=True)
    provider = models.CharField(max_length=40, blank=True)
    provider_ref = models.CharField(max_length=128, blank=True)
    # Normalised provider data (names, dates, categories). Encrypted: it holds personal data.
    details = EncryptedJSONField(null=True, blank=True)
    # Shown to the driver when they must enter a code again.
    driver_message = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["application", "type"], name="uq_check_application_type")]

    def reset(self) -> None:
        self.status = CheckStatus.PENDING
        self.reasons = []
        self.details = None
        self.provider = ""
        self.provider_ref = ""
        self.driver_message = ""
        self.completed_at = None


class Evidence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="evidence")
    kind = models.CharField(max_length=30, choices=EvidenceKind.choices)
    content_type = models.CharField(max_length=100)
    storage_key = models.CharField(max_length=255)
    size_bytes = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class AuditEvent(models.Model):
    """Append-only record of everything that happened to an application."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="audit_events")
    actor = models.CharField(max_length=128)
    action = models.CharField(max_length=64, db_index=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
