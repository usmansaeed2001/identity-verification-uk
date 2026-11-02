import re

import pytest
from django.core import mail
from rest_framework.test import APIClient

from accounts.models import User

pytestmark = pytest.mark.django_db


class Browser(APIClient):
    """Behaves like the React app: reads the CSRF cookie and sends it back as a header on every request."""

    def generic(self, method, path, *args, **kwargs):
        if "csrftoken" in self.cookies:
            kwargs["HTTP_X_CSRFTOKEN"] = self.cookies["csrftoken"].value
        return super().generic(method, path, *args, **kwargs)


@pytest.fixture
def browser() -> APIClient:
    client = Browser(enforce_csrf_checks=True)
    client.get("/api/auth/csrf")
    return client


def link_in_last_email() -> str:
    return re.search(r"http\S+", mail.outbox[-1].body).group(0)


def test_register_logs_in_and_sends_a_verification_link(browser):
    r = browser.post("/api/auth/register", {"email": "Driver@Example.com", "password": "a-long-password-1"})
    assert r.status_code == 201, r.json()
    assert r.json()["email"] == "driver@example.com"
    assert r.json()["email_verified"] is False
    assert browser.get("/api/auth/me").json()["email"] == "driver@example.com"

    token = link_in_last_email().split("token=")[1]
    assert browser.post("/api/auth/verify-email", {"token": token}).status_code == 200
    assert browser.get("/api/auth/me").json()["email_verified"] is True


def test_register_rejects_weak_passwords_and_duplicates(browser):
    r = browser.post("/api/auth/register", {"email": "a@example.com", "password": "short"})
    assert r.status_code == 400
    assert "password" in r.json()["errors"]
    User.objects.create_user("taken@example.com", "a-long-password-1")
    r = browser.post("/api/auth/register", {"email": "TAKEN@example.com", "password": "a-long-password-1"})
    assert "already exists" in r.json()["detail"]


def test_login_and_logout(browser):
    User.objects.create_user("d@example.com", "a-long-password-1")
    assert browser.post("/api/auth/login", {"email": "d@example.com", "password": "wrong"}).status_code in (401, 403)
    r = browser.post("/api/auth/login", {"email": "D@example.com", "password": "a-long-password-1"})
    assert r.status_code == 200
    assert browser.post("/api/auth/logout").status_code == 200
    assert browser.get("/api/auth/me").status_code == 403


def test_login_needs_the_csrf_token():
    User.objects.create_user("d@example.com", "a-long-password-1")
    client = APIClient(enforce_csrf_checks=True)
    r = client.post("/api/auth/login", {"email": "d@example.com", "password": "a-long-password-1"})
    assert r.status_code == 403


def test_password_reset(browser):
    User.objects.create_user("d@example.com", "a-long-password-1")
    assert browser.post("/api/auth/password-reset", {"email": "nobody@example.com"}).status_code == 200
    assert mail.outbox == []
    browser.post("/api/auth/password-reset", {"email": "d@example.com"})
    query = link_in_last_email().split("?")[1]
    params = dict(p.split("=", 1) for p in query.split("&"))
    r = browser.post("/api/auth/password-reset/confirm", {**params, "password": "a-new-long-password-2"})
    assert r.status_code == 200
    again = browser.post("/api/auth/password-reset/confirm", {**params, "password": "another-password-3"})
    assert again.status_code == 400  # each link works once
    login = browser.post("/api/auth/login", {"email": "d@example.com", "password": "a-new-long-password-2"})
    assert login.status_code == 200


def test_auth_endpoints_are_throttled(browser):
    for _ in range(10):
        browser.post("/api/auth/login", {"email": "x@example.com", "password": "nope"})
    assert browser.post("/api/auth/login", {"email": "x@example.com", "password": "nope"}).status_code == 429
