from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from common.permissions import REVIEWERS_GROUP


class Command(BaseCommand):
    help = "Create (or update) a staff account that can use the reviewer portal."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("password")

    def handle(self, email: str, password: str, **options):
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User.objects.create_user(email, password, is_staff=True)
        else:
            user.set_password(password)
            user.is_staff = True
            user.save()
        group, _ = Group.objects.get_or_create(name=REVIEWERS_GROUP)
        user.groups.add(group)
        self.stdout.write(self.style.SUCCESS(f"Reviewer ready: {user.email}"))
