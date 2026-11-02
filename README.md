# Driver Onboarding

UK HGV drivers sign up, prove who they are and that they can work and drive, and an onboarding team reviews them.

| Part | Stack |
|---|---|
| `backend/` | Django 5.2 + DRF, Celery + Redis, PostgreSQL 16 |
| `frontend/` | React 19 + TypeScript + Vite + Tailwind, one responsive web app for phones and desktops |
| `legacy-fastapi/` | The earlier FastAPI service, kept for reference. Its Check Share Code client, decision rules and validation were ported into `backend/`. |

## What's real and what's simulated

| Check | How | Status |
|---|---|---|
| Right to work (share code) | [Check Share Code](https://checksharecode.co.uk) → gov.uk | **Live** |
| Driving licence (DVLA check code) | Check Share Code → gov.uk | **Live** |
| Photo ID + live face scan | Driver uploads ID, then a 3-frame camera scan | Photos captured, encrypted and shown to reviewers. **Matching is simulated: it always matches.** |
| Name + date of birth | Compared with the Home Office record | Real |
| Driver CPC | Not available from DVLA check codes | Driver can upload their DQC card; a reviewer checks it |

**Today, no driver is approved automatically.** A simulated check can never pass an application on its own (`onboarding/decision.py`), an accepted share code always needs a person to compare the Home Office photo, and CPC needs a person. Every application that doesn't fail a check goes to a reviewer, who sees the selfies, the photo ID and the Home Office photo side by side.

British and Irish citizens don't have share codes. They skip that step, and the reviewer is told to see their original passport in person (or use a certified identity provider).

## Run it

You need Docker. Put your Check Share Code key in `.env` (see `.env.example`):

```sh
CHECKSHARECODE_API_KEY=rtw_test_...   # sandbox; rtw_live_... runs real, paid gov.uk checks
EMPLOYER_NAME=Your Company Ltd        # gov.uk records this as the employer making the check
```

Then:

```sh
docker compose up -d --build
docker compose exec backend python manage.py create_reviewer reviewer@example.com 'choose-a-password'
```

| URL | What |
|---|---|
| http://localhost:8080 | The app. Drivers register; reviewers sign in and land on `/staff` |
| http://localhost:8025 | Mailpit: every email the app sends |
| http://localhost:8080/admin/ | Django admin (read-only back office). Needs `python manage.py createsuperuser` |

### On a phone

The camera only works over HTTPS. Use a tunnel:

```sh
cloudflared tunnel --url http://localhost:8080
```

Open the `https://….trycloudflare.com` URL on the phone. `*.trycloudflare.com` is already allowed. Set `FRONTEND_URL` in `.env` to that URL so links in emails point to it.

### Developing without rebuilding containers

```sh
docker compose up -d postgres redis mailpit         # Postgres is on host port 5433
cd backend  && uv sync && uv run python manage.py migrate && uv run python manage.py runserver
cd backend  && uv run celery -A config worker -P solo --loglevel=info     # live checks run here
cd frontend && npm install && npm run dev                                 # http://localhost:5173, proxies /api
```

To skip the worker, set `CELERY_TASK_ALWAYS_EAGER=true`. Live checks then run inside the web request, which takes 15–40 seconds.

## Testing with the sandbox key

A `rtw_test_` key never reaches gov.uk and doesn't use paid checks. Applications checked with it are flagged **Test data**. The real sandbox returns fixed test people:

| Input | Result |
|---|---|
| Share code `AA1 AA1 AA1` | Accepted, for **ALEX TEST SAMPLE**. Enter the first name "Alex Test" and last name "Sample" for the name check to pass. |
| Share code `CC3 CC3 CC3` / `DD4 DD4 DD4` | Not found / can't be used: the driver is asked for a new code |
| Licence `NOWAK803147T99AB`, check code `AAAA` + any 4 characters | A clean **car** licence (AM, B). **No HGV entitlement, so the application fails.** |
| Check code `CCCC…` / `DDDD…` / `GGGG…` | 6 points / refused / busy (retried) |

Each check code works once. Change the last 4 characters to try again.

Because the sandbox has no HGV licence, a sandbox application always ends "not approved". The approval path (review → approve, or send steps back to the driver) is covered by the backend tests, which use an in-process fake of the API. To demo approval live, use a real driver with an `rtw_live_` key.

With a live key, sandbox codes are refused before any request leaves the service, so they never use a paid check.

## Driver journey

1. **Sign up** with email and password. Email verification is sent but not required for the demo (`REQUIRE_EMAIL_VERIFICATION=false`).
2. **About you**: name and date of birth as on the ID, UK mobile, and "Are you a British or Irish citizen?"
3. **Consent**: checks, photos and DVLA sharing.
4. **Photo ID**: passport, UK photocard licence or EU/EEA ID card (front and back for cards). Taken with the phone camera or chosen from files, resized in the browser.
5. **Face scan**: live front camera only, 3 prompted photos (straight, left, right).
6. **Right to work**: share code, checked live. Skipped for British/Irish citizens.
7. **Driving licence**: licence number and DVLA check code, checked live. Optional DQC card photo.
8. **Check and send**, then a status page. If a reviewer sends steps back, the driver sees the reviewer's message and can change only those steps.

The paid checks (6 and 7) only run after steps 1–5 are done, so drivers who drop out early don't use them up. Each application gets 3 attempts per check per day, and the whole service gets 20 a day (`LIVE_CHECK_*` in `.env`).

## Reviewer portal

`/staff` lists applications by status, with search by name or email. The detail page shows:

- the photos side by side
- every check with its reasons and a **Simulated** badge where it applies
- the Home Office and DVLA PDFs
- the driver's details and the audit trail

Reviewers can approve or reject (a note is required), or send chosen steps back to the driver with a message. Every evidence view is written to the audit trail.

## API

Session cookie + CSRF (`X-CSRFToken` header from the `csrftoken` cookie; call `GET /api/auth/csrf` first).

| | |
|---|---|
| `/api/auth/` | `csrf`, `me`, `register`, `login`, `logout`, `verify-email`, `verify-email/resend`, `password-reset`, `password-reset/confirm` |
| `/api/driver/` | `application` (GET), `profile` (PUT), `consent`, `identity/document` (multipart `front`, `back`), `identity/selfie` (multipart `frames` ×3), `right-to-work`, `licence`, `licence/dqc` (multipart `photo`), `submit` |
| `/api/staff/applications` | list (`?status=&route=&q=`), `{id}`, `{id}/evidence/{evidence_id}`, `{id}/review`, `{id}/request-action` |

## Data protection

- Names, dates of birth, phone numbers, licence numbers, codes and check details are encrypted in the database with Fernet (`DATA_ENCRYPTION_KEYS`, newest first, so keys can be rotated). Evidence files are encrypted on disk.
- Share codes and DVLA check codes are cleared as soon as a check has used them. If the provider is down, the share code stays encrypted on the check so a reviewer can check gov.uk by hand.
- Uploaded photos are re-encoded as JPEG, which drops EXIF data such as GPS location.
- Drivers never see check results, only their own details and the outcome.
- `config.settings.prod` refuses to start with the development `SECRET_KEY` or encryption key.
- **Before real drivers:** do a DPIA. Once a real face matcher runs, photos become biometric special-category data. Check Share Code isn't a registered Digital Verification Service Provider and doesn't name its operator, so production needs a named data processor and a DPA. The employer stays legally responsible for right to work checks.

## Tests

```sh
cd backend  && uv run pytest            # 2,246 tests: decision rules, provider mapping, every API flow, auth, permissions
cd frontend && npm test                 # validation + wizard steps
cd frontend && npx playwright install chromium && npx playwright test
                                        # end to end on a Pixel 7 viewport with a fake camera, against docker compose
                                        # and the real Check Share Code sandbox
```

## Not done yet (demo scope)

- A real identity provider (document authenticity, liveness, face match), e.g. Onfido, Yoti or iProov. Add one class beside `backend/providers/identity_stub.py` and select it in `registry.py`.
- DVLA ADD for licence checks with CPC data and repeat checks without a new code.
- Scheduled jobs: deleting photos after a retention period, and right to work expiry reminders (`rtw_expires_at` is stored).
- S3 storage for evidence (it's on a Docker volume now).
- An email provider for production. Django's email settings are in place; Amazon SES (London) via `django-anymail` is the likely choice.
- Production hardening: CSP/HSTS, `config.settings.prod` in the containers (they run development settings with `DEBUG=True`).
