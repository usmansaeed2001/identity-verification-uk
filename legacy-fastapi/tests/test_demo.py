"""Click through the demo pages the way a person would (forms + redirects)."""

import re

from tests.conftest import drain


async def start(client, **form):
    data = {
        "first_name": "Tomasz",
        "last_name": "Nowak",
        "dob": "1987-03-14",
        "route": "share_code",
        "mode": "mock",
        "scenario": "all_pass",
        **form,
    }
    response = await client.post("/demo/start", data=data)
    assert response.status_code == 303, response.text
    return response.headers["location"].rsplit("/", 1)[-1]


async def test_start_page_offers_mock_only(client):
    page = await client.get("/demo")
    assert page.status_code == 200
    assert "No provider configured" in page.text
    assert re.search(r'id="mode-live"[^>]*disabled', page.text)


async def test_share_code_journey_end_to_end(app, client):
    case_id = await start(client)
    base = f"/demo/driver/{case_id}"

    assert (await client.get(base)).headers["location"] == f"{base}/consent"
    consent = await client.get(f"{base}/consent")
    assert "Simulated vendor screen" in consent.text and "Step 1 of 5" in consent.text

    refused = await client.post(f"{base}/consent", data={})
    assert refused.status_code == 422 and "Tick the box" in refused.text

    assert (await client.post(f"{base}/consent", data={"agree": "yes"})).headers["location"] == f"{base}/document"
    assert (await client.post(f"{base}/document")).headers["location"] == f"{base}/selfie"
    assert (await client.post(f"{base}/selfie")).headers["location"] == f"{base}/share-code"

    bad_code = await client.post(f"{base}/share-code", data={"share_code": "R12 3AB C45", "dob": "1987-03-14"})
    assert bad_code.status_code == 422 and "start with W" in bad_code.text
    ok_code = await client.post(f"{base}/share-code", data={"share_code": "W12 3AB C45", "dob": "1987-03-14"})
    assert ok_code.headers["location"] == f"{base}/licence"

    licence_page = await client.get(f"{base}/licence")
    assert "NOWAK803147T99AB" in licence_page.text
    done = await client.post(f"{base}/licence", data={"licence_number": "NOWAK803147T99AB", "dvla_consent": "yes"})
    assert done.headers["location"] == f"{base}/checking"

    checking = await client.get(f"{base}/checking")
    assert "Checking your details" in checking.text and 'hx-trigger="every 2s"' in checking.text

    await drain(app)
    status = await client.get(f"{base}/status")
    assert "Cleared to drive" in status.text and "hx-trigger" not in status.text

    admin = await client.get(f"/demo/admin/cases/{case_id}")
    assert "verification.completed" in admin.text
    assert "Delivered · signature verified" in admin.text
    assert "Home Office right to work profile" in admin.text
    assert "Categories: B, C1, C, C+E" in admin.text

    listing = await client.get("/demo/admin")
    assert "Tomasz Nowak" in listing.text and "PASSED" in listing.text


async def test_british_route_has_no_share_code_step_and_review_works(app, client):
    case_id = await start(client, route="british_irish", scenario="name_mismatch")
    base = f"/demo/driver/{case_id}"
    await client.post(f"{base}/consent", data={"agree": "yes"})
    await client.post(f"{base}/document")
    assert (await client.post(f"{base}/selfie")).headers["location"] == f"{base}/licence"
    assert (await client.get(f"{base}/share-code")).status_code == 404
    await client.post(f"{base}/licence", data={"licence_number": "NOWAK803147T99AB", "dvla_consent": "yes"})
    await drain(app)

    admin = await client.get(f"/demo/admin/cases/{case_id}")
    assert "MANUAL_REVIEW" in admin.text and "Review this case" in admin.text
    assert "middle name" in admin.text

    too_short = await client.post(f"/demo/admin/cases/{case_id}/review", data={"decision": "approve", "note": "x"})
    assert too_short.status_code == 422
    approved = await client.post(
        f"/demo/admin/cases/{case_id}/review",
        data={"decision": "approve", "note": "Middle name shown on passport.", "reviewed_by": "Demo reviewer"},
    )
    assert approved.status_code == 303
    await drain(app)
    admin = await client.get(f"/demo/admin/cases/{case_id}")
    assert "PASSED" in admin.text and "Approved" in admin.text


async def test_evidence_link_redirects_to_signed_pdf(app, client):
    case_id = await start(client)
    base = f"/demo/driver/{case_id}"
    await client.post(f"{base}/licence", data={"licence_number": "NOWAK803147T99AB", "dvla_consent": "yes"})
    await drain(app)
    admin = await client.get(f"/demo/admin/cases/{case_id}")
    link = re.search(rf'href="(/demo/admin/cases/{case_id}/evidence/[^"]+)"', admin.text).group(1)
    redirect = await client.get(link)
    assert redirect.status_code == 303 and redirect.headers["location"].startswith("/v1/evidence/")
    pdf = await client.get(redirect.headers["location"])
    assert pdf.headers["content-type"] == "application/pdf"


async def test_starting_a_scenario_that_does_not_fit_shows_the_api_error(client):
    response = await client.post(
        "/demo/start",
        data={
            "first_name": "A",
            "last_name": "B",
            "dob": "1990-01-01",
            "route": "british_irish",
            "mode": "mock",
            "scenario": "rtw_expired",
        },
    )
    assert response.status_code == 422
    assert "The API refused the request" in response.text
