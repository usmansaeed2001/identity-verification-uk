"""Live checks through Check Share Code. Each takes 15-40 seconds, so they run in the worker."""

import logging
from datetime import date

from celery import shared_task
from django.conf import settings

from onboarding import services
from onboarding.enums import CheckStatus, CheckType
from onboarding.models import Application
from providers import checksharecode
from providers.base import DriverInputError, ProviderError, ProviderTimeout

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


def _running(application_id: str, check_type: CheckType) -> Application | None:
    application = Application.objects.filter(pk=application_id).first()
    if application is None or application.get_check(check_type).status != CheckStatus.RUNNING:
        return None  # finished, or reset by a reviewer while queued
    return application


@shared_task
def run_rtw_check(application_id: str, attempt: int = 1) -> None:
    application = _running(application_id, CheckType.RIGHT_TO_WORK)
    if application is None:
        return
    try:
        result = checksharecode.check_right_to_work(
            application.share_code, date.fromisoformat(application.share_code_dob)
        )
    except DriverInputError as exc:
        services.rtw_needs_new_code(application, exc.message, exc.code)
    except ProviderTimeout as exc:
        if attempt < MAX_ATTEMPTS:
            logger.info("Right to work check %s: retrying after %s", application_id, exc)
            run_rtw_check.apply_async((application_id, attempt + 1), countdown=settings.LIVE_CHECK_RETRY_DELAY_SECONDS)
        else:
            services.rtw_unavailable(application, f"The Home Office check didn't answer after {MAX_ATTEMPTS} tries.")
    except ProviderError as exc:
        logger.error("Right to work check %s refused: %s", application_id, exc)
        services.rtw_unavailable(application, f"The right to work check couldn't run: {exc}")
    else:
        services.rtw_completed(application, result)


@shared_task
def run_licence_check(application_id: str, attempt: int = 1) -> None:
    application = _running(application_id, CheckType.DVLA_LICENCE)
    if application is None:
        return
    try:
        result = checksharecode.check_licence(application.licence_number, application.dvla_check_code)
    except DriverInputError as exc:
        services.licence_needs_new_code(application, exc.message, exc.code)
    except ProviderTimeout as exc:
        # Only raised when DVLA never saw the code, so trying again won't use it up.
        if attempt < MAX_ATTEMPTS:
            logger.info("Licence check %s: retrying after %s", application_id, exc)
            run_licence_check.apply_async(
                (application_id, attempt + 1), countdown=settings.LIVE_CHECK_RETRY_DELAY_SECONDS
            )
        else:
            services.licence_unavailable(application, f"DVLA didn't answer after {MAX_ATTEMPTS} tries.")
    except ProviderError as exc:
        logger.error("Licence check %s refused: %s", application_id, exc)
        services.licence_unavailable(application, f"The licence check couldn't run: {exc}")
    else:
        services.licence_completed(application, result)
