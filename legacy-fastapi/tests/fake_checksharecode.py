"""In-process stand-in for api.checksharecode.co.uk, following its OpenAPI spec and sandbox codes."""

import base64
import json

import httpx

PDF = "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4 fake gov.uk output").decode()
PHOTO = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()


def _error(status: int, code: str, message: str, **extra) -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": code, "message": message, **extra}})


class FakeCheckShareCode:
    def __init__(self):
        self.requests: list[dict] = []
        self.used_check_codes: set[str] = set()
        # Responses to return before the normal rules, e.g. a BUSY then a success.
        self.forced: list[httpx.Response] = []

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"path": request.url.path, "auth": request.headers.get("authorization"), "body": body})
        if self.forced:
            return self.forced.pop(0)
        if request.url.path == "/v1/check/right-to-work":
            return self.right_to_work(body)
        if request.url.path == "/v1/check/driving-licence":
            return self.driving_licence(body)
        return _error(404, "ENDPOINT_NOT_FOUND", "No such endpoint.")

    def right_to_work(self, body: dict) -> httpx.Response:
        code = body["share_code"].replace(" ", "").upper()
        if code == "CC3CC3CC3":
            return _error(404, "NOT_FOUND", "No gov.uk record matches the share code and date of birth.")
        if code == "DD4DD4DD4":
            return _error(422, "SHARE_CODE_UNUSABLE", "gov.uk will not use this share code for this check.")
        if code == "GG7GG7GG7":
            return _error(503, "BUSY", "Server busy.")
        rejected = code == "BB2BB2BB2"
        time_limited = code == "AA1AA1AA1"
        return httpx.Response(
            200,
            json={
                "outcome": "REJECTED" if rejected else "ACCEPTED",
                "title": "Right to work",
                "name": "TOMASZ NOWAK",
                "date_of_birth": "14 March 1987",
                "details": (
                    "They do not have the right to work in the UK."
                    if rejected
                    else "They have the right to work in the UK from 1 January 2025 until 1 January 2027."
                ),
                "start_date": "2025-01-01",
                "expiry_date": "2027-01-01" if time_limited else None,
                "recheck_date": "2027-01-01" if time_limited else None,
                "conditions": ["They can work in any job."] if not rejected else [],
                "restrictions": [],
                "reference": "RTW-TEST-123",
                "company_name": body["company_name"],
                "check_date": "2026-10-29",
                "share_code": code,
                "photo_data_url": PHOTO,
                "pdf_data_url": PDF,
                "checked_at": "2026-10-29T10:00:00Z",
            },
        )

    def driving_licence(self, body: dict) -> httpx.Response:
        code = body["check_code"].replace(" ", "")
        if code in self.used_check_codes:
            return _error(
                409, "CHECK_CODE_ALREADY_USED", "This code was sent in the last 21 days.", check_code_used=True
            )
        self.used_check_codes.add(code)
        prefix = code[:4]
        if prefix == "DDDD":
            return _error(422, "CHECK_CODE_UNUSABLE", "DVLA did not accept the code.", check_code_used=True)
        if prefix == "EEEE":
            return _error(502, "GOVUK_UNEXPECTED", "Unexpected DVLA response.", check_code_used=True)
        if prefix == "GGGG":
            self.used_check_codes.discard(code)
            return _error(503, "BUSY", "Server busy.", check_code_used=False)
        categories = ["B", "C1"] if prefix == "BBBB" else ["B", "C1", "C", "C+E"]
        points = 6 if prefix == "CCCC" else 0
        return httpx.Response(
            200,
            json={
                "outcome": "ACCEPTED",
                "title": "Driving licence",
                "name": "MR TOMASZ NOWAK",
                "driving_status": "Current full licence",
                "licence_number_last8": body["licence_number"][-8:],
                "issue_number": "12",
                "licence_valid_from": "2020-01-01",
                "licence_valid_to": "2030-01-01",
                "offences": 2 if points else 0,
                "points": points,
                "has_penalties": bool(points),
                "automatic_only": False,
                "entitlements": [
                    {
                        "category": c,
                        "kind": "full",
                        "valid_from": "2010-01-01",
                        "valid_to": "2030-01-01",
                        "automatic_only": False,
                        "restrictions": [],
                        "description": None,
                    }
                    for c in categories
                ]
                + [
                    {
                        "category": "D",
                        "kind": "provisional",
                        "valid_from": None,
                        "valid_to": None,
                        "automatic_only": False,
                        "restrictions": [],
                        "description": None,
                    }
                ],
                "flags": [{"code": "points_6_to_8", "severity": "medium"}] if points else [],
                "viewed_at": "2026-10-29T10:00:00+00:00",
                "pdf_data_url": PDF,
                "checked_at": "2026-10-29T10:00:00Z",
            },
        )
