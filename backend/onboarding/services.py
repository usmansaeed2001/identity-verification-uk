"""The onboarding lifecycle: what the driver can do when, the live checks, submission and review."""

import logging
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.emails import send_driver_update
from common import storage
from common.images import clean_photo
from onboarding.decision import IdentitySource, compare_identity, decide
from onboarding.enums import (
    DOCUMENTS_WITH_BACK,
    DONE_CHECK_STATUSES,
    EDITABLE_STATUSES,
    ApplicationStatus,
    CheckStatus,
    CheckType,
    EvidenceKind,
    ReviewDecision,
    Route,
    Step,
)
from onboarding.models import Application, AuditEvent, Check, Evidence
from providers import checksharecode
from providers.base import CheckOutcome, EvidenceFile, Person
from providers.registry import identity_provider

logger = logging.getLogger(__name__)

SELFIE_FRAMES = 3
BRITISH_IRISH_REASON = (
    "British or Irish citizen: see the driver's original passport (or Irish passport card) in person, "
    "or use a certified identity provider, before approving."
)
LIVE_CHECK_ACTIONS = {CheckType.RIGHT_TO_WORK: "rtw_check_requested", CheckType.DVLA_LICENCE: "licence_check_requested"}


class OnboardingError(Exception):
    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code:
            self.status_code = status_code


def audit(application: Application, actor: str, action: str, **detail) -> None:
    AuditEvent.objects.create(application=application, actor=actor, action=action, detail=detail)


def driver_actor(application: Application) -> str:
    return f"driver:{application.user_id}"


def get_or_create_application(user) -> Application:
    application, created = Application.objects.get_or_create(user=user)
    if created:
        audit(application, f"driver:{user.pk}", "application_started")
    return application


# --- Steps -------------------------------------------------------------------


def steps_for(application: Application) -> list[Step]:
    steps = [Step.PROFILE, Step.CONSENT, Step.DOCUMENT, Step.SELFIE]
    if application.route != Route.BRITISH_IRISH:
        steps.append(Step.RIGHT_TO_WORK)
    steps.append(Step.LICENCE)
    return steps


def _evidence_count(application: Application, kind: EvidenceKind) -> int:
    return application.evidence.filter(kind=kind).count()


def _check_done(application: Application, check_type: CheckType) -> bool:
    check = application.checks.filter(type=check_type).first()
    return bool(check and check.status in DONE_CHECK_STATUSES)


def step_done(application: Application, step: Step) -> bool:
    if step in application.reopened_steps:
        return False
    if step == Step.PROFILE:
        return bool(application.first_name and application.last_name and application.dob and application.route)
    if step == Step.CONSENT:
        return bool(application.consent_at and application.dvla_consent_at)
    if step == Step.DOCUMENT:
        if not application.document_type or not _evidence_count(application, EvidenceKind.ID_FRONT):
            return False
        return application.document_type not in DOCUMENTS_WITH_BACK or bool(
            _evidence_count(application, EvidenceKind.ID_BACK)
        )
    if step == Step.SELFIE:
        return _evidence_count(application, EvidenceKind.SELFIE) >= SELFIE_FRAMES
    if step == Step.RIGHT_TO_WORK:
        return _check_done(application, CheckType.RIGHT_TO_WORK)
    if step == Step.LICENCE:
        return _check_done(application, CheckType.DVLA_LICENCE)
    return False


def step_editable(application: Application, step: Step) -> bool:
    if application.status == ApplicationStatus.DRAFT:
        return True
    return application.status == ApplicationStatus.ACTION_REQUIRED and step in application.reopened_steps


def _require_editable(application: Application, step: Step) -> None:
    if not step_editable(application, step):
        raise OnboardingError("This part of your application can't be changed now.", 409)


def _require_done(application: Application, *steps: Step) -> None:
    missing = [s.label for s in steps if not step_done(application, s) and s not in application.reopened_steps]
    if missing:
        raise OnboardingError(f"Finish these steps first: {', '.join(missing)}.", 409)


def _step_completed(application: Application, step: Step) -> None:
    if step in application.reopened_steps:
        application.reopened_steps = [s for s in application.reopened_steps if s != step]
        application.save(update_fields=["reopened_steps", "updated_at"])


# --- Driver actions ------------------------------------------------------------


def save_profile(application: Application, first_name: str, last_name: str, dob: date, phone: str, route: str) -> None:
    _require_editable(application, Step.PROFILE)
    if route != application.route and _check_done(application, CheckType.RIGHT_TO_WORK):
        # The right to work evidence depends on the route, so start that step again.
        application.get_check(CheckType.RIGHT_TO_WORK).delete()
    application.first_name = first_name.strip()
    application.last_name = last_name.strip()
    application.dob = dob.isoformat()
    application.phone = phone
    application.route = route
    application.save()
    _step_completed(application, Step.PROFILE)
    audit(application, driver_actor(application), "profile_saved", route=route)


def give_consent(application: Application) -> None:
    _require_editable(application, Step.CONSENT)
    now = timezone.now()
    application.consent_at = now
    application.dvla_consent_at = now
    application.save(update_fields=["consent_at", "dvla_consent_at", "updated_at"])
    audit(application, driver_actor(application), "consent_given", data=True, photos=True, dvla=True)


def _replace_evidence(application: Application, kind: EvidenceKind, files: list[EvidenceFile]) -> None:
    """Old photos of the same kind are deleted: we keep only what the decision is based on."""
    for old in application.evidence.filter(kind=kind):
        storage.delete(old.storage_key)
        old.delete()
    for f in files:
        store_evidence(application, f)


def store_evidence(application: Application, f: EvidenceFile) -> Evidence:
    key = storage.save(str(application.id), f.data)
    return Evidence.objects.create(
        application=application, kind=f.kind, content_type=f.content_type, storage_key=key, size_bytes=len(f.data)
    )


def save_document(application: Application, document_type: str, front, back=None) -> None:
    _require_editable(application, Step.DOCUMENT)
    _require_done(application, Step.PROFILE, Step.CONSENT)
    if document_type in DOCUMENTS_WITH_BACK and back is None:
        raise OnboardingError("Add a photo of the back of the card too.")
    front_jpeg = clean_photo(front)
    back_jpeg = clean_photo(back) if back is not None and document_type in DOCUMENTS_WITH_BACK else None
    with transaction.atomic():
        application.document_type = document_type
        application.save(update_fields=["document_type", "updated_at"])
        _replace_evidence(
            application, EvidenceKind.ID_FRONT, [EvidenceFile(EvidenceKind.ID_FRONT, "image/jpeg", front_jpeg)]
        )
        _replace_evidence(
            application,
            EvidenceKind.ID_BACK,
            [EvidenceFile(EvidenceKind.ID_BACK, "image/jpeg", back_jpeg)] if back_jpeg else [],
        )
    _step_completed(application, Step.DOCUMENT)
    audit(application, driver_actor(application), "document_uploaded", document_type=document_type)


def save_selfie(application: Application, frames: list) -> None:
    _require_editable(application, Step.SELFIE)
    _require_done(application, Step.PROFILE, Step.CONSENT)
    if len(frames) != SELFIE_FRAMES:
        raise OnboardingError(f"The face scan needs {SELFIE_FRAMES} photos. Start the scan again.")
    jpegs = [clean_photo(f) for f in frames]
    with transaction.atomic():
        _replace_evidence(
            application, EvidenceKind.SELFIE, [EvidenceFile(EvidenceKind.SELFIE, "image/jpeg", j) for j in jpegs]
        )
    _step_completed(application, Step.SELFIE)
    audit(application, driver_actor(application), "selfie_captured", frames=len(jpegs))


def save_dqc_card(application: Application, photo) -> None:
    _require_editable(application, Step.LICENCE)
    jpeg = clean_photo(photo)
    _replace_evidence(application, EvidenceKind.DQC_CARD, [EvidenceFile(EvidenceKind.DQC_CARD, "image/jpeg", jpeg)])
    audit(application, driver_actor(application), "dqc_card_uploaded")


def _check_live_limits(application: Application, check_type: CheckType) -> None:
    if not checksharecode.is_configured():
        raise OnboardingError("Live checks aren't set up yet. Ask the team to add the Check Share Code key.", 503)
    since = timezone.now() - timedelta(days=1)
    action = LIVE_CHECK_ACTIONS[check_type]
    mine = AuditEvent.objects.filter(application=application, action=action, created_at__gte=since).count()
    if mine >= settings.LIVE_CHECK_ATTEMPTS_PER_DAY:
        raise OnboardingError("You've tried this check too many times today. Try again tomorrow.", 429)
    everyone = AuditEvent.objects.filter(action__in=LIVE_CHECK_ACTIONS.values(), created_at__gte=since).count()
    if everyone >= settings.LIVE_CHECK_GLOBAL_DAILY_LIMIT:
        raise OnboardingError("We can't run more checks today. Try again tomorrow.", 429)


def _start_live_check(application: Application, check_type: CheckType) -> Check:
    check = application.get_check(check_type)
    if check.status == CheckStatus.RUNNING:
        raise OnboardingError("That check is already running.", 409)
    _check_live_limits(application, check_type)
    check.reset()
    check.status = CheckStatus.RUNNING
    check.save()
    audit(application, driver_actor(application), LIVE_CHECK_ACTIONS[check_type])
    return check


def request_rtw_check(application: Application, share_code: str, dob: date) -> None:
    from onboarding.tasks import run_rtw_check

    _require_editable(application, Step.RIGHT_TO_WORK)
    if application.route != Route.SHARE_CODE:
        raise OnboardingError("British and Irish citizens don't need a share code.", 409)
    # Paid checks run last, so drivers who drop out early don't use them up.
    _require_done(application, Step.PROFILE, Step.CONSENT, Step.DOCUMENT, Step.SELFIE)
    with transaction.atomic():
        _start_live_check(application, CheckType.RIGHT_TO_WORK)
        application.share_code = share_code
        application.share_code_dob = dob.isoformat()
        application.save(update_fields=["share_code", "share_code_dob", "updated_at"])
        transaction.on_commit(lambda: run_rtw_check.delay(str(application.id)))


def request_licence_check(application: Application, licence_number: str, check_code: str) -> None:
    from onboarding.tasks import run_licence_check

    _require_editable(application, Step.LICENCE)
    _require_done(application, Step.PROFILE, Step.CONSENT, Step.DOCUMENT, Step.SELFIE)
    with transaction.atomic():
        _start_live_check(application, CheckType.DVLA_LICENCE)
        application.licence_number = licence_number
        application.dvla_check_code = check_code
        application.save(update_fields=["licence_number", "dvla_check_code", "updated_at"])
        transaction.on_commit(lambda: run_licence_check.delay(str(application.id)))


# --- Live check results (run by Celery) ---------------------------------------------


def _apply_outcome(check: Check, outcome: CheckOutcome, provider: str, provider_ref: str = "") -> None:
    check.status = outcome.status
    check.reasons = outcome.reasons
    check.details = outcome.details or None
    check.provider = provider
    check.provider_ref = provider_ref
    check.driver_message = ""
    check.completed_at = timezone.now()
    check.save()


def rtw_needs_new_code(application: Application, message: str, code: str) -> None:
    check = application.get_check(CheckType.RIGHT_TO_WORK)
    check.reset()
    check.driver_message = message
    check.save()
    clear_rtw_codes(application)
    audit(application, "system", "rtw_check_needs_new_code", code=code)


def clear_rtw_codes(application: Application) -> None:
    application.share_code = None
    application.share_code_dob = None
    application.save(update_fields=["share_code", "share_code_dob", "updated_at"])


def rtw_unavailable(application: Application, reason: str) -> None:
    check = application.get_check(CheckType.RIGHT_TO_WORK)
    # The reviewer needs the code to check it on gov.uk themselves; it stays encrypted.
    outcome = CheckOutcome(
        CheckStatus.UNCLEAR,
        [reason, "Check the share code yourself at gov.uk/view-right-to-work."],
        {"share_code": application.share_code, "date_of_birth": application.share_code_dob},
    )
    _apply_outcome(check, outcome, "checksharecode")
    clear_rtw_codes(application)
    audit(application, "system", "rtw_check_unavailable", reason=reason)


def rtw_completed(application: Application, result) -> None:
    check = application.get_check(CheckType.RIGHT_TO_WORK)
    _apply_outcome(check, result.right_to_work, "checksharecode", result.provider_ref)
    _replace_evidence(
        application,
        EvidenceKind.RTW_PROFILE_PDF,
        [e for e in result.evidence if e.kind == EvidenceKind.RTW_PROFILE_PDF],
    )
    _replace_evidence(
        application,
        EvidenceKind.HOME_OFFICE_PHOTO,
        [e for e in result.evidence if e.kind == EvidenceKind.HOME_OFFICE_PHOTO],
    )
    application.rtw_expires_at = result.rtw_expires_at
    application.is_test = application.is_test or checksharecode.is_sandbox()
    application.save(update_fields=["rtw_expires_at", "is_test", "updated_at"])
    clear_rtw_codes(application)
    _step_completed(application, Step.RIGHT_TO_WORK)
    audit(application, "system", "rtw_check_completed", status=check.status, sandbox=checksharecode.is_sandbox())


def licence_needs_new_code(application: Application, message: str, code: str) -> None:
    check = application.get_check(CheckType.DVLA_LICENCE)
    check.reset()
    check.driver_message = message
    check.save()
    clear_licence_code(application)
    audit(application, "system", "licence_check_needs_new_code", code=code)


def clear_licence_code(application: Application) -> None:
    application.dvla_check_code = None
    application.save(update_fields=["dvla_check_code", "updated_at"])


def licence_unavailable(application: Application, reason: str) -> None:
    check = application.get_check(CheckType.DVLA_LICENCE)
    _apply_outcome(
        check, CheckOutcome(CheckStatus.UNCLEAR, [reason, "Check the licence at gov.uk/check-driving-information."]), ""
    )
    clear_licence_code(application)
    audit(application, "system", "licence_check_unavailable", reason=reason)


def licence_completed(application: Application, result) -> None:
    _apply_outcome(
        application.get_check(CheckType.DVLA_LICENCE), result.licence, "checksharecode_dvla", result.provider_ref
    )
    _apply_outcome(application.get_check(CheckType.DRIVER_CPC), result.cpc, "checksharecode_dvla")
    _replace_evidence(application, EvidenceKind.DVLA_SUMMARY_PDF, result.evidence)
    application.is_test = application.is_test or checksharecode.is_sandbox()
    application.save(update_fields=["is_test", "updated_at"])
    clear_licence_code(application)
    _step_completed(application, Step.LICENCE)
    audit(application, "system", "licence_check_completed", status=result.licence.status)


# --- Submission ------------------------------------------------------------------


def _load_images(application: Application, *kinds: EvidenceKind) -> list[bytes]:
    return [storage.load(e.storage_key) for e in application.evidence.filter(kind__in=kinds)]


def submit(application: Application) -> None:
    if application.status not in EDITABLE_STATUSES:
        raise OnboardingError("Your application has already been sent.", 409)
    _require_done(application, *steps_for(application))
    if application.reopened_steps:
        raise OnboardingError("Finish the steps the reviewer asked about first.", 409)
    if application.checks.filter(status=CheckStatus.RUNNING).exists():
        raise OnboardingError("Wait for the checks to finish first.", 409)

    with transaction.atomic():
        identity = identity_provider().verify(
            application.document_type,
            _load_images(application, EvidenceKind.ID_FRONT, EvidenceKind.ID_BACK),
            _load_images(application, EvidenceKind.SELFIE),
        )
        provider_name = identity_provider().name
        _apply_outcome(application.get_check(CheckType.IDENTITY_DOCUMENT), identity.identity_document, provider_name)
        _apply_outcome(application.get_check(CheckType.LIVENESS), identity.liveness, provider_name)
        _apply_outcome(application.get_check(CheckType.FACE_MATCH), identity.face_match, provider_name)

        rtw = application.get_check(CheckType.RIGHT_TO_WORK)
        if application.route == Route.BRITISH_IRISH:
            _apply_outcome(
                rtw, CheckOutcome(CheckStatus.UNCLEAR, [BRITISH_IRISH_REASON], {"method": "manual"}), "manual"
            )

        sources = []
        person = (rtw.details or {}).get("person")
        if person:
            p = Person.from_dict(person)
            sources.append(IdentitySource("Home Office record", p.full_name, p.dob))
        if identity.person_on_document:
            p = identity.person_on_document
            sources.append(IdentitySource("photo ID", p.full_name, p.dob))
        status, reasons = compare_identity(
            application.first_name, application.last_name, application.date_of_birth, sources
        )
        _apply_outcome(application.get_check(CheckType.NAME_DOB_MATCH), CheckOutcome(status, reasons), "onboarding")

        cpc = application.get_check(CheckType.DRIVER_CPC)
        if cpc.status == CheckStatus.PENDING:  # the DVLA lookup couldn't run, so it never set this
            cpc.status = CheckStatus.UNCLEAR
            cpc.reasons = [checksharecode.CPC_NOT_AVAILABLE_REASON]
            cpc.completed_at = timezone.now()
        dqc_note = (
            "The driver uploaded a DQC card photo: check the name and expiry date."
            if _evidence_count(application, EvidenceKind.DQC_CARD)
            else "The driver didn't upload a DQC card. Ask for it before approving."
        )
        cpc.reasons = [r for r in cpc.reasons if not r.startswith("The driver ")] + [dqc_note]
        cpc.save()

        decision = decide(application.checks.all())
        now = timezone.now()
        application.status = decision.status
        application.submitted_at = now
        application.decided_at = (
            now if decision.status in (ApplicationStatus.PASSED, ApplicationStatus.FAILED) else None
        )
        application.reopened_steps = []
        application.action_message = ""
        application.save()
        audit(application, driver_actor(application), "submitted", outcome=decision.status, reasons=decision.reasons)

    if decision.status == ApplicationStatus.FAILED:
        send_driver_update(
            application.user,
            "Your driver application",
            "We couldn't approve your driver application. Sign in to see what happens next.",
        )
    else:
        send_driver_update(
            application.user,
            "We've got your driver application",
            "Thanks for sending your driver application. Our team will review it and email you.",
        )


# --- Reviewer actions -------------------------------------------------------------


def review(application: Application, reviewer, decision: str, note: str) -> None:
    if application.status != ApplicationStatus.MANUAL_REVIEW:
        raise OnboardingError("Only applications waiting for review can be approved or rejected.", 409)
    now = timezone.now()
    application.status = ApplicationStatus.PASSED if decision == ReviewDecision.APPROVE else ApplicationStatus.FAILED
    application.review_decision = decision
    application.review_note = note
    application.reviewed_by = reviewer
    application.reviewed_at = now
    application.decided_at = now
    application.save()
    audit(application, f"staff:{reviewer.email}", f"review_{decision}", note=note)
    if decision == ReviewDecision.APPROVE:
        send_driver_update(application.user, "You're approved", "Good news: your driver application is approved.")
    else:
        send_driver_update(
            application.user,
            "Your driver application",
            "We couldn't approve your driver application. Sign in to see what happens next.",
        )


REOPENABLE_STEPS = (Step.PROFILE, Step.DOCUMENT, Step.SELFIE, Step.RIGHT_TO_WORK, Step.LICENCE)


def request_action(application: Application, reviewer, steps: list[str], message: str) -> None:
    if application.status != ApplicationStatus.MANUAL_REVIEW:
        raise OnboardingError("You can only send back applications waiting for review.", 409)
    steps = [Step(s) for s in steps]
    if Step.RIGHT_TO_WORK in steps and application.route == Route.BRITISH_IRISH:
        raise OnboardingError("This driver has no share code step.", 400)
    with transaction.atomic():
        for step, check_type in ((Step.RIGHT_TO_WORK, CheckType.RIGHT_TO_WORK), (Step.LICENCE, CheckType.DVLA_LICENCE)):
            if step in steps:
                check = application.get_check(check_type)
                check.reset()
                check.save()
        application.status = ApplicationStatus.ACTION_REQUIRED
        application.reopened_steps = [str(s) for s in steps]
        application.action_message = message
        application.save()
        audit(
            application,
            f"staff:{reviewer.email}",
            "action_requested",
            steps=application.reopened_steps,
            message=message,
        )
    send_driver_update(
        application.user,
        "We need something else for your driver application",
        f"Our team needs you to update part of your application:\n\n{message}",
    )
