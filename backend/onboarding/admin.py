"""Back-office fallback. Reviewers normally use the React portal; this is read-only on purpose."""

from django.contrib import admin

from onboarding.models import Application, AuditEvent, Check, Evidence


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


class CheckInline(ReadOnlyInline):
    model = Check
    fields = ["type", "status", "reasons", "provider", "completed_at"]


class EvidenceInline(ReadOnlyInline):
    model = Evidence
    fields = ["kind", "content_type", "size_bytes", "created_at"]


class AuditInline(ReadOnlyInline):
    model = AuditEvent
    fields = ["created_at", "actor", "action", "detail"]


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "status", "route", "is_test", "submitted_at", "updated_at"]
    list_filter = ["status", "route", "is_test"]
    search_fields = ["user__email"]
    inlines = [CheckInline, EvidenceInline, AuditInline]
    fields = [
        "user",
        "status",
        "route",
        "first_name",
        "last_name",
        "dob",
        "phone",
        "document_type",
        "rtw_expires_at",
        "reopened_steps",
        "action_message",
        "is_test",
        "submitted_at",
        "decided_at",
        "review_decision",
        "review_note",
        "reviewed_by",
        "reviewed_at",
    ]
    readonly_fields = fields

    def has_add_permission(self, request) -> bool:
        return False
