from rest_framework.permissions import BasePermission

REVIEWERS_GROUP = "reviewers"


def is_reviewer(user) -> bool:
    if not (user and user.is_authenticated and user.is_staff):
        return False
    return user.is_superuser or user.groups.filter(name=REVIEWERS_GROUP).exists()


class IsReviewer(BasePermission):
    message = "Only reviewers can do that."

    def has_permission(self, request, view) -> bool:
        return is_reviewer(request.user)


class IsDriver(BasePermission):
    """Staff accounts don't go through onboarding themselves."""

    message = "Staff accounts can't make a driver application."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and not request.user.is_staff)
