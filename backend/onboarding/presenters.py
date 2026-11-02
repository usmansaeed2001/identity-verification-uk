"""What the driver sees of their own application. Check results stay with the reviewers."""

from django.conf import settings

from onboarding import services
from onboarding.enums import DOCUMENTS_WITH_BACK, ApplicationStatus, CheckStatus, CheckType, EvidenceKind
from onboarding.models import Application
from onboarding.validation import mask
from providers import checksharecode

OUTCOME_MESSAGES = {
    ApplicationStatus.MANUAL_REVIEW: "Thanks. Our team is reviewing your application and will email you.",
    ApplicationStatus.PASSED: "You're approved. We'll be in touch about your first shift.",
    ApplicationStatus.FAILED: "One of our checks didn't pass. Contact us if you think this is wrong.",
    ApplicationStatus.ACTION_REQUIRED: "We need you to update part of your application.",
}


def _live_check(application: Application, check_type: CheckType) -> dict:
    check = application.checks.filter(type=check_type).first()
    if check is None or (check.status == CheckStatus.PENDING and not check.driver_message):
        return {"state": "not_started", "message": ""}
    if check.status == CheckStatus.RUNNING:
        return {"state": "running", "message": ""}
    if check.status == CheckStatus.PENDING:
        return {"state": "needs_new_code", "message": check.driver_message}
    return {"state": "done", "message": ""}


def driver_application(application: Application, user) -> dict:
    steps = services.steps_for(application)
    done = {step: services.step_done(application, step) for step in steps}
    next_step = next((s for s in steps if not done[s]), None)
    evidence_kinds = list(application.evidence.values_list("kind", flat=True))
    return {
        "id": str(application.id),
        "status": application.status,
        "status_label": ApplicationStatus(application.status).label,
        "outcome_message": OUTCOME_MESSAGES.get(application.status, ""),
        "route": application.route or None,
        "steps": [
            {
                "key": str(s),
                "label": s.label,
                "done": done[s],
                "editable": services.step_editable(application, s),
            }
            for s in steps
        ],
        "next_step": str(next_step) if next_step else None,
        "can_submit": application.status in (ApplicationStatus.DRAFT, ApplicationStatus.ACTION_REQUIRED)
        and next_step is None,
        "profile": {
            "first_name": application.first_name or "",
            "last_name": application.last_name or "",
            "dob": application.dob or "",
            "phone": application.phone or "",
        },
        "consent_given": bool(application.consent_at and application.dvla_consent_at),
        "document": {
            "type": application.document_type or None,
            "has_front": EvidenceKind.ID_FRONT in evidence_kinds,
            "has_back": EvidenceKind.ID_BACK in evidence_kinds,
            "needs_back": application.document_type in DOCUMENTS_WITH_BACK,
        },
        "selfie_frames": evidence_kinds.count(EvidenceKind.SELFIE),
        "right_to_work": _live_check(application, CheckType.RIGHT_TO_WORK),
        "licence": {
            **_live_check(application, CheckType.DVLA_LICENCE),
            "licence_number": mask(application.licence_number, 5),
            "has_dqc_card": EvidenceKind.DQC_CARD in evidence_kinds,
        },
        "action": {"steps": application.reopened_steps, "message": application.action_message},
        "submitted_at": application.submitted_at,
        "live_checks": {"configured": checksharecode.is_configured(), "sandbox": checksharecode.is_sandbox()},
        "email_verified": user.email_verified,
        "email_verification_required": settings.REQUIRE_EMAIL_VERIFICATION,
    }
