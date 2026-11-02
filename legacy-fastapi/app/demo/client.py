"""The demo plays the host platform: it calls our own /v1 API, signed, entirely server-side.

Requests go through the ASGI app in-process, so the API key never reaches a browser.
"""

import json
import time
from datetime import date
from typing import Any

import httpx
from fastapi import FastAPI

from app.config import Settings
from app.security import sign


class HostApiError(Exception):
    def __init__(self, status_code: int, body: dict[str, Any]):
        error = body.get("error", {}) if isinstance(body, dict) else {}
        self.status_code = status_code
        self.message = error.get("message", f"The API returned HTTP {status_code}.")
        self.fields = {f["field"]: f["message"] for f in error.get("fields", [])}
        super().__init__(self.message)


class HostClient:
    def __init__(self, app: FastAPI, settings: Settings):
        self.settings = settings
        self._client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://service.internal")

    async def __aenter__(self) -> "HostClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode() if payload is not None else b""
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.settings.host_api_key,
            "X-Timestamp": timestamp,
            "X-Signature": f"sha256={sign(self.settings.host_signing_secret, timestamp, body)}",
        }
        response = await self._client.request(method, path, content=body, headers=headers)
        data = response.json() if response.content else {}
        if not response.is_success:
            raise HostApiError(response.status_code, data)
        return data

    async def create_verification(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/v1/verifications", payload)

    async def get_verification(self, case_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/verifications/{case_id}")

    async def submit_share_code(self, case_id: str, share_code: str, dob: date) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/v1/verifications/{case_id}/share-code",
            {"share_code": share_code, "date_of_birth": dob.isoformat()},
        )

    async def submit_licence(self, case_id: str, licence_number: str, check_code: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"licence_number": licence_number, "dvla_consent": True}
        if check_code:
            payload["check_code"] = check_code
        return await self._request("POST", f"/v1/verifications/{case_id}/licence", payload)

    async def review(self, case_id: str, decision: str, note: str, reviewed_by: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/v1/verifications/{case_id}/review",
            {"decision": decision, "note": note, "reviewed_by": reviewed_by},
        )

    async def evidence(self, case_id: str) -> list[dict[str, Any]]:
        return (await self._request("GET", f"/v1/verifications/{case_id}/evidence"))["items"]
