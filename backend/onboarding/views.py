from django.conf import settings
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from common.images import InvalidImage
from common.permissions import IsDriver
from onboarding import services
from onboarding.presenters import driver_application
from onboarding.serializers import (
    ConsentSerializer,
    DocumentSerializer,
    LicenceSerializer,
    PhotoSerializer,
    ProfileSerializer,
    ShareCodeSerializer,
)
from providers import checksharecode


class OnboardingAPIException(APIException):
    def __init__(self, error: services.OnboardingError):
        super().__init__(error.message)
        self.status_code = error.status_code


class DriverView(APIView):
    permission_classes = [IsDriver]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def application(self):
        return services.get_or_create_application(self.request.user)

    def respond(self, application):
        application.refresh_from_db()
        return Response(driver_application(application, self.request.user))

    def handle_exception(self, exc):
        if isinstance(exc, services.OnboardingError):
            exc = OnboardingAPIException(exc)
        elif isinstance(exc, InvalidImage):
            exc = ValidationError({"photo": [str(exc)]})
        return super().handle_exception(exc)

    def validated(self, serializer_class):
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class ApplicationView(DriverView):
    def get(self, request):
        return self.respond(self.application())


class ProfileView(DriverView):
    def put(self, request):
        data = self.validated(ProfileSerializer)
        application = self.application()
        services.save_profile(application, **data)
        return self.respond(application)


class ConsentView(DriverView):
    def post(self, request):
        self.validated(ConsentSerializer)
        application = self.application()
        services.give_consent(application)
        return self.respond(application)


class DocumentView(DriverView):
    def post(self, request):
        data = self.validated(DocumentSerializer)
        application = self.application()
        services.save_document(application, data["document_type"], data["front"], data.get("back"))
        return self.respond(application)


class SelfieView(DriverView):
    def post(self, request):
        frames = request.FILES.getlist("frames")
        for frame in frames:
            PhotoSerializer(data={"photo": frame}).is_valid(raise_exception=True)
        application = self.application()
        services.save_selfie(application, frames)
        return self.respond(application)


class LiveCheckView(DriverView):
    def preflight(self):
        if not checksharecode.is_configured():
            raise services.OnboardingError("Live checks aren't set up yet. Ask the team to add the API key.", 503)
        if settings.REQUIRE_EMAIL_VERIFICATION and not self.request.user.email_verified:
            raise services.OnboardingError("Confirm your email address first. Check your inbox for the link.", 403)


class RightToWorkView(LiveCheckView):
    def post(self, request):
        self.preflight()
        data = self.validated(ShareCodeSerializer)
        application = self.application()
        services.request_rtw_check(application, data["share_code"], data.get("dob") or application.date_of_birth)
        return self.respond(application)


class LicenceView(LiveCheckView):
    def post(self, request):
        self.preflight()
        data = self.validated(LicenceSerializer)
        application = self.application()
        services.request_licence_check(application, data["licence_number"], data["check_code"])
        return self.respond(application)


class DqcCardView(DriverView):
    def post(self, request):
        data = self.validated(PhotoSerializer)
        application = self.application()
        services.save_dqc_card(application, data["photo"])
        return self.respond(application)


class SubmitView(DriverView):
    def post(self, request):
        application = self.application()
        services.submit(application)
        return self.respond(application)
