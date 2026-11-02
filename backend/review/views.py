from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from common import storage
from common.permissions import IsReviewer
from onboarding import services
from onboarding.enums import ApplicationStatus, CheckType, EvidenceKind, ReviewDecision, Route
from onboarding.models import Application

LIST_LIMIT = 500


class ReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=ReviewDecision.choices)
    note = serializers.CharField(max_length=2000)


class RequestActionSerializer(serializers.Serializer):
    steps = serializers.ListField(
        child=serializers.ChoiceField(choices=[str(s) for s in services.REOPENABLE_STEPS]), min_length=1
    )
    message = serializers.CharField(max_length=2000)


class ReviewerView(APIView):
    permission_classes = [IsReviewer]

    def handle_exception(self, exc):
        if isinstance(exc, services.OnboardingError):
            api_exc = APIException(exc.message)
            api_exc.status_code = exc.status_code
            exc = api_exc
        return super().handle_exception(exc)


def _summary_row(application: Application) -> dict:
    return {
        "id": str(application.id),
        "email": application.user.email,
        "name": application.full_name,
        "status": application.status,
        "status_label": ApplicationStatus(application.status).label,
        "route": application.route or None,
        "is_test": application.is_test,
        "submitted_at": application.submitted_at,
        "updated_at": application.updated_at,
    }


class ApplicationListView(ReviewerView):
    def get(self, request):
        qs = Application.objects.select_related("user").order_by("-submitted_at", "-updated_at")
        if status := request.query_params.get("status"):
            qs = qs.filter(status=status)
        if route := request.query_params.get("route"):
            qs = qs.filter(route=route)
        rows = [_summary_row(a) for a in qs[:LIST_LIMIT]]
        # Names are encrypted in the database, so search happens here rather than in SQL.
        if q := request.query_params.get("q", "").strip().lower():
            rows = [r for r in rows if q in r["email"].lower() or q in r["name"].lower()]
        counts = dict(Application.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
        return Response({"results": rows, "counts": counts})


def _detail(application: Application) -> dict:
    checks = application.ordered_checks()
    return {
        **_summary_row(application),
        "profile": {
            "first_name": application.first_name,
            "last_name": application.last_name,
            "dob": application.dob,
            "phone": application.phone,
        },
        "document_type": application.document_type or None,
        "licence_number": application.licence_number,
        "rtw_expires_at": application.rtw_expires_at,
        "decided_at": application.decided_at,
        "review": {
            "decision": application.review_decision or None,
            "note": application.review_note,
            "by": application.reviewed_by.email if application.reviewed_by else None,
            "at": application.reviewed_at,
        },
        "action": {"steps": application.reopened_steps, "message": application.action_message},
        "checks": [
            {
                "type": c.type,
                "label": CheckType(c.type).label,
                "status": c.status,
                "reasons": c.reasons,
                "details": c.details or {},
                "provider": c.provider,
                "simulated": bool((c.details or {}).get("simulated")),
                "completed_at": c.completed_at,
            }
            for c in checks
        ],
        "evidence": [
            {
                "id": str(e.id),
                "kind": e.kind,
                "label": EvidenceKind(e.kind).label,
                "content_type": e.content_type,
                "url": f"/api/staff/applications/{application.id}/evidence/{e.id}",
                "created_at": e.created_at,
            }
            for e in application.evidence.all()
        ],
        "audit": [
            {"at": a.created_at, "actor": a.actor, "action": a.action, "detail": a.detail}
            for a in application.audit_events.all()
        ],
        "reopenable_steps": [
            {"key": str(s), "label": s.label}
            for s in services.REOPENABLE_STEPS
            if not (str(s) == "right_to_work" and application.route == Route.BRITISH_IRISH)
        ],
    }


class ApplicationDetailView(ReviewerView):
    def get(self, request, pk):
        application = get_object_or_404(Application.objects.select_related("user", "reviewed_by"), pk=pk)
        return Response(_detail(application))


class EvidenceView(ReviewerView):
    def get(self, request, pk, evidence_id):
        application = get_object_or_404(Application, pk=pk)
        evidence = get_object_or_404(application.evidence, pk=evidence_id)
        services.audit(application, f"staff:{request.user.email}", "evidence_viewed", kind=evidence.kind)
        response = HttpResponse(storage.load(evidence.storage_key), content_type=evidence.content_type)
        response["Cache-Control"] = "no-store"
        response["Content-Disposition"] = f'inline; filename="{evidence.kind}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ReviewDecisionView(ReviewerView):
    def post(self, request, pk):
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = get_object_or_404(Application, pk=pk)
        services.review(
            application, request.user, serializer.validated_data["decision"], serializer.validated_data["note"]
        )
        return Response(_detail(application))


class RequestActionView(ReviewerView):
    def post(self, request, pk):
        serializer = RequestActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = get_object_or_404(Application, pk=pk)
        services.request_action(
            application, request.user, serializer.validated_data["steps"], serializer.validated_data["message"]
        )
        return Response(_detail(application))
