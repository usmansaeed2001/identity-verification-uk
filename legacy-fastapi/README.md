# Driver Verification Service

Checks that a UK truck driver can work in the UK, is who they say they are, and holds a valid HGV licence. Another platform (the **host**) calls it over a signed REST API and gets the result back as a signed webhook.

| Check | How (production) | Provider |
|---|---|---|
| Right to work | Home Office share code check, or certified IDSP passport check for British/Irish citizens | RTW vendor (not yet chosen) |
| Identity | Document authenticity + selfie liveness + face match | RTW vendor |
| HGV licence | DVLA: C / C+E entitlement, disqualification, points, Driver CPC | DVLA ADD intermediary (not yet chosen) |
| Name / DOB | Compares the host's details with every source | This service |

> **Current status:** two modes.
> - **Mock**: every check is simulated from a chosen scenario. It's refused in production.
> - **Real (share code route only)**: the driver's share code and DVLA check code are checked on gov.uk through [Check Share Code](https://checksharecode.co.uk), with a free sandbox and 10 free live checks a month.
>
> Identity verification (document + selfie) isn't switched on yet, so a reviewer compares the driver with the Home Office photo before approving. British/Irish passport checks need a registered identity provider and aren't available in real mode.

## Real checks with Check Share Code

Set these in `.env` and restart:

```sh
RTW_PROVIDER=checksharecode
LICENCE_PROVIDER=checksharecode
CHECKSHARECODE_API_KEY=rtw_test_...   # sandbox; rtw_live_... runs real gov.uk checks
EMPLOYER_NAME=Your Company Ltd        # gov.uk records this as the employer making the check
```

Then pick **Real** on `/demo`. The flow is:

1. The host opens a case with `"mode": "live"` and `"route": "share_code"`.
2. The host sends the driver's share code to `POST /v1/verifications/{id}/share-code` with `share_code` and `date_of_birth`. The Home Office check runs in the background and takes about 20 seconds.
3. The host sends the licence to `POST /v1/verifications/{id}/licence` with `licence_number`, `check_code` and `dvla_consent: true`. The driver makes the check code at gov.uk/view-driving-licence; it lasts 21 days and works once.
4. If gov.uk can't use a code (no record found, expired, code refused), the host gets a `verification.driver_action_required` webhook. The same check reopens so the driver can send a new code.
5. An accepted share code always ends in `MANUAL_REVIEW`. The reviewer compares the Home Office photo with the driver in person or by video call, and checks the Driver CPC card, because DVLA's check code service doesn't show CPC. The reviewer then approves or rejects.

Things to know before using live keys:

- Check Share Code is an independent service that drives the gov.uk pages for you. It isn't a registered RtW DVSP, the Home Office doesn't endorse it, and its operator isn't named on its site. That's fine for a demo with testers who agree. Production needs a named data processor and a DPA.
- The employer stays legally responsible for the right to work check.
- Share codes, dates of birth and check codes are stored encrypted and cleared as soon as a check has used them. Photos and PDFs are kept as evidence.

## Run it

**Docker (Postgres + Redis + arq worker):**

```sh
docker compose up -d --build
open http://localhost:8000/demo        # demo
open http://localhost:8000/docs        # API reference
```

**Without Docker (SQLite, jobs run in-process):**

```sh
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:create_app --factory --reload
```

**On a phone:** the camera needs HTTPS, so expose the service through a tunnel and tell it its public URL:

```sh
cloudflared tunnel --url http://localhost:8000
# then set PUBLIC_BASE_URL=https://<random>.trycloudflare.com in .env and restart
```

## The demo (`/demo`, never mounted in production)

1. **Start a check** plays the host. It creates a verification through the signed API and picks a test scenario.
2. **Driver screens** show what the vendor's own app will show in production: consent, document photo, selfie, share code (share code route only), and licence number with DVLA consent. These are labelled "Simulated vendor screen". Photos stay on the device and are never uploaded.
3. **Checking** updates live as the mock vendor's webhook and the DVLA lookup arrive, then shows the outcome.
4. **Cases → case view** shows what the host received: each check with its details, the evidence PDF, the signed webhooks with their payloads, the full audit trail, and approve/reject buttons for cases waiting for manual review.

| Scenario | Outcome |
|---|---|
| `all_pass` | PASSED |
| `rtw_expired` (share code route only) | FAILED |
| `face_mismatch` | MANUAL_REVIEW |
| `name_mismatch` | MANUAL_REVIEW |
| `no_hgv_entitlement` | FAILED |
| `cpc_expired` | FAILED |
| `dvla_timeout` (retried twice) | MANUAL_REVIEW |

## API

Every `/v1` request needs:

- `X-API-Key`: the host's key
- `X-Timestamp`: Unix seconds, within 5 minutes of the server clock
- `X-Signature`: `sha256=` + hex HMAC-SHA256 of `"<timestamp>.<raw body>"`, keyed with `HOST_SIGNING_SECRET` (for a GET, the body is empty)

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/verifications` | Open a case. Returns `id`, `status` and `driver_url` (send the driver there) |
| GET | `/v1/verifications/{id}` | Status, each check with reasons, and review details |
| POST | `/v1/verifications/{id}/licence` | Licence number + `dvla_consent: true`, if not sent at creation |
| POST | `/v1/verifications/{id}/review` | `approve` / `reject` a `MANUAL_REVIEW` case, with a note |
| GET | `/v1/verifications/{id}/evidence` | Signed download links that expire after 5 minutes |

```json
POST /v1/verifications
{
  "external_driver_id": "drv_48213",
  "first_name": "Tomasz", "last_name": "Nowak", "dob": "1987-03-14",
  "route": "share_code",
  "licence_number": "NOWAK803147T99AB", "dvla_consent": true,
  "callback_url": "https://host.example/hooks/idv",
  "mode": "mock", "mock_scenario": "all_pass"
}
```

The case moves through `CREATED → AWAITING_DRIVER → IN_PROGRESS → PASSED | FAILED | MANUAL_REVIEW`. Any failed check fails the case at once. If nothing failed but something is unclear, the case goes to a person. A case passes only when every check passes.

**Webhooks to the host:** `verification.completed`, `verification.requires_review` and `rtw.expiring` (28 days before time-limited permission ends). They're signed the same way, with `X-Webhook-Timestamp` and `X-Webhook-Signature` keyed by `WEBHOOK_SIGNING_SECRET`, and retried with backoff up to 5 times. Every payload includes `is_test`, so the host should ignore `true` in production data.

## Layout

```
app/api/          host API, provider webhooks, auth
app/domain/       models, decision rules, validation, schemas
app/providers/    provider interfaces, mock RTW vendor, mock DVLA, scenarios
app/services/     orchestrator (case lifecycle), notifier, evidence store, audit
app/workers/      jobs + queue (inline or arq), arq worker entry point
app/demo/         demo pages (Jinja2 + HTMX)
alembic/          migrations
```

Adding a real vendor means writing one adapter that implements `RtwProvider` or `LicenceProvider` in `app/providers/base.py`, and then selecting it in `app/providers/registry.py`.

## Data protection

- Names, dates of birth, licence numbers and provider details are encrypted in the database with Fernet (`DATA_ENCRYPTION_KEY`). Evidence files are encrypted before they're stored.
- Logs mask share codes and licence numbers.
- The audit trail is append-only and records every state change and reviewer decision.
- Test cases and their evidence are deleted after 24 hours. Live evidence is kept until employment ends; the host endpoint to signal that is still to be built.
- Production refuses to start with any development secret.

## Tests

```sh
uv run pytest
```

This covers every pass/fail/unclear combination of the decision rules, all scenarios end to end with real webhook delivery, auth and replay protection, the production lockdown, the expiry and retention jobs, and click-throughs of the demo pages.

## Not done yet

- Identity verification (document + selfie face match) through a registered RtW DVSP, and British/Irish passport checks.
- DVLA ADD for licence checks with Driver CPC data and repeat checks without a new code from the driver.
- A host endpoint to record employment end, so live evidence retention can be applied.
- The MinIO image is no longer publicly available, so Compose stores evidence on a volume. `EVIDENCE_BACKEND=s3` supports a real bucket.
