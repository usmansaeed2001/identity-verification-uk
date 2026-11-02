import io

import pytest
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import User
from common.permissions import REVIEWERS_GROUP
from providers import checksharecode
from tests.fake_checksharecode import FakeCheckShareCode

LICENCE = "NOWAK803147T99AB"


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    """Every test talks to the fake: nothing ever reaches the real Check Share Code API."""
    fake = FakeCheckShareCode()
    monkeypatch.setattr(checksharecode, "transport", fake.transport())
    return fake


@pytest.fixture(autouse=True)
def _clear_throttles():
    cache.clear()


def photo(name: str = "photo.jpg", size=(800, 600)) -> SimpleUploadedFile:
    out = io.BytesIO()
    Image.new("RGB", size, (200, 180, 160)).save(out, format="JPEG")
    return SimpleUploadedFile(name, out.getvalue(), content_type="image/jpeg")


@pytest.fixture
def driver(db) -> APIClient:
    client = APIClient()
    user = User.objects.create_user("tomasz@example.com", "a-long-password-1")
    client.force_authenticate(user)
    client.user = user
    return client


@pytest.fixture
def reviewer(db) -> APIClient:
    user = User.objects.create_user("reviewer@example.com", "a-long-password-1", is_staff=True)
    user.groups.add(Group.objects.get_or_create(name=REVIEWERS_GROUP)[0])
    client = APIClient()
    client.force_authenticate(user)
    return client


def fill_identity(client: APIClient, route: str = "share_code", first_name: str = "Tomasz") -> dict:
    """Profile, consent, photo ID and face scan: everything before the paid checks."""
    r = client.put(
        "/api/driver/profile",
        {
            "first_name": first_name,
            "last_name": "Nowak",
            "dob": "1987-03-14",
            "phone": "07700 900123",
            "route": route,
        },
        format="json",
    )
    assert r.status_code == 200, r.json()
    r = client.post("/api/driver/consent", {"data_consent": True, "dvla_consent": True}, format="json")
    assert r.status_code == 200, r.json()
    r = client.post(
        "/api/driver/identity/document",
        {"document_type": "passport", "front": photo()},
        format="multipart",
    )
    assert r.status_code == 200, r.json()
    r = client.post(
        "/api/driver/identity/selfie",
        {"frames": [photo("1.jpg"), photo("2.jpg"), photo("3.jpg")]},
        format="multipart",
    )
    assert r.status_code == 200, r.json()
    return r.json()


def run_checks(client: APIClient, share_code: str | None = "AA1AA1AA1", check_code: str = "AAAA1234") -> dict:
    if share_code:
        r = client.post("/api/driver/right-to-work", {"share_code": share_code}, format="json")
        assert r.status_code == 200, r.json()
    r = client.post("/api/driver/licence", {"licence_number": LICENCE, "check_code": check_code}, format="json")
    assert r.status_code == 200, r.json()
    return client.get("/api/driver/application").json()
