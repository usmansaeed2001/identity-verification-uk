import { expect, test, type Page } from '@playwright/test'

/*
 * The whole journey on a phone-sized screen: sign up, photo ID, live face scan, then the right to work
 * and licence checks against the real Check Share Code sandbox (never reaches gov.uk). A reviewer then
 * opens the case and sees the photos, the Home Office record and why it wasn't approved.
 *
 * The sandbox's share code AA1AA1AA1 belongs to "ALEX TEST SAMPLE", and every sandbox licence is a
 * car licence (AM, B) with no HGV entitlement, so a sandbox application always ends "not approved".
 * The approval path is covered by the backend tests (backend/tests/test_onboarding.py).
 *
 * Needs: docker compose up, a rtw_test_ key in .env, and a reviewer:
 *   docker compose exec backend python manage.py create_reviewer reviewer@example.com review-demo-pass-1
 */

const REVIEWER = { email: 'reviewer@example.com', password: process.env.E2E_REVIEWER_PASSWORD ?? 'review-demo-pass-1' }
const MAILPIT = process.env.E2E_MAILPIT_URL ?? 'http://localhost:8025'

/** A plain JPEG made in the browser, standing in for a photo of an ID card. */
async function idPhoto(page: Page): Promise<Buffer> {
  const dataUrl = await page.evaluate(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 1000
    canvas.height = 630
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#d9e6f2'
    ctx.fillRect(0, 0, 1000, 630)
    ctx.fillStyle = '#7a8a99'
    ctx.fillRect(60, 120, 260, 340)
    ctx.fillStyle = '#123'
    ctx.font = '48px sans-serif'
    ctx.fillText('NOWAK, TOMASZ', 380, 200)
    return canvas.toDataURL('image/jpeg', 0.9)
  })
  return Buffer.from(dataUrl.split(',')[1], 'base64')
}

test('a driver onboards on a phone and a reviewer sees the result', async ({ page, browser, request }) => {
  const email = `driver-${Date.now()}@example.com`
  const checkCode = `AAAA${String(Date.now()).slice(-4)}` // each DVLA check code works once

  // Sign up
  await page.goto('/register')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Create a password').fill('a-long-demo-password-1')
  await page.getByRole('button', { name: 'Create account' }).click()

  // About you
  await expect(page.getByRole('heading', { name: 'About you' })).toBeVisible()
  await page.getByLabel('First name').fill('Alex Test') // the sandbox's Home Office record
  await page.getByLabel('Last name').fill('Sample')
  await page.getByLabel('Date of birth').fill('1987-03-14')
  await page.getByLabel('Mobile number').fill('07700 900123')
  await page.getByRole('radio', { name: /No/ }).check()
  await page.getByRole('button', { name: 'Save and continue' }).click()

  // Consent
  await expect(page.getByRole('heading', { name: 'Before you start' })).toBeVisible()
  await page.getByRole('checkbox', { name: /checks above/ }).check()
  await page.getByRole('checkbox', { name: /DVLA/ }).check()
  await page.getByRole('button', { name: 'Agree and continue' }).click()

  // Photo ID
  await expect(page.getByRole('heading', { name: 'Photo ID' })).toBeVisible()
  await page.getByRole('radio', { name: 'Passport' }).check()
  await page.getByLabel('Take photo').setInputFiles({ name: 'passport.jpg', mimeType: 'image/jpeg', buffer: await idPhoto(page) })
  await expect(page.getByAltText('Photo page preview')).toBeVisible()
  await page.getByRole('button', { name: 'Upload and continue' }).click()

  // Live face scan (fake camera)
  await expect(page.getByRole('heading', { name: 'Face scan' })).toBeVisible()
  await page.getByRole('button', { name: 'Start face scan' }).click()
  await expect(page.getByText('Look straight at the camera')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Use these photos' })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByAltText(/Face scan photo/)).toHaveCount(3)
  await page.getByRole('button', { name: 'Use these photos' }).click()

  // Right to work: real call to the Check Share Code sandbox
  await expect(page.getByRole('heading', { name: 'Right to work' })).toBeVisible()
  await expect(page.getByText('Test mode')).toBeVisible()
  await page.getByLabel('Share code').fill('AA1 AA1 AA1')
  await page.getByRole('button', { name: 'Check my right to work' }).click()
  await expect(page.getByText('Thanks. This check is done.')).toBeVisible({ timeout: 120_000 })
  await page.getByRole('button', { name: 'Continue' }).click()

  // Driving licence: real call to the sandbox
  await expect(page.getByRole('heading', { name: 'Driving licence' })).toBeVisible()
  await page.getByLabel('Driving licence number').fill('NOWAK803147T99AB')
  await page.getByLabel('DVLA check code').fill(checkCode)
  await page.getByRole('button', { name: 'Check my licence' }).click()
  await expect(page.getByText('Thanks. This check is done.')).toBeVisible({ timeout: 120_000 })
  await page.getByRole('button', { name: 'Continue' }).click()

  // Check and send
  await expect(page.getByRole('heading', { name: 'Check and send' })).toBeVisible()
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Send application' }).click()
  await expect(page.getByRole('heading', { name: "We couldn't approve your application" })).toBeVisible()
  await page.screenshot({ path: 'test-results/driver-outcome.png', fullPage: true })

  // Mailpit caught the emails
  const inbox = await (await request.get(`${MAILPIT}/api/v1/search?query=to:${encodeURIComponent(email)}`)).json()
  const subjects = inbox.messages.map((m: { Subject: string }) => m.Subject)
  expect(subjects).toEqual(expect.arrayContaining(['Confirm your email address', 'Your driver application']))

  // Reviewer, on a laptop-sized screen
  const staff = await browser.newPage({ viewport: { width: 1366, height: 900 } })
  await staff.goto('/login')
  await staff.getByLabel('Email address').fill(REVIEWER.email)
  await staff.getByLabel('Password').fill(REVIEWER.password)
  await staff.getByRole('button', { name: 'Sign in' }).click()
  await expect(staff.getByRole('heading', { name: 'Driver applications' })).toBeVisible()
  await staff.getByRole('tab', { name: /Not approved/ }).click()
  await staff.getByRole('cell', { name: email }).getByRole('link').click()

  await expect(staff.getByText('Test data (sandbox key)')).toBeVisible()
  await expect(staff.getByText('Identity checks simulated')).toBeVisible()
  await expect(staff.getByRole('listitem').filter({ hasText: /^The licence has no full entitlement/ })).toBeVisible()
  await expect(staff.getByText('A check failed, so this application was not approved.')).toBeVisible()
  await expect(staff.getByText('ALEX TEST SAMPLE', { exact: false }).first()).toBeVisible() // Home Office record
  await expect(staff.getByRole('button', { name: 'Approve' })).toHaveCount(0)
  // Every photo in the comparison panel actually loads (decrypted, staff-only).
  const photos = staff.locator('figure img')
  await expect(photos).toHaveCount(5) // 3 selfies, passport, Home Office photo
  for (const img of await photos.all()) {
    await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true)
  }
  await staff.screenshot({ path: 'test-results/reviewer-detail.png', fullPage: true })

  // A driver can never open the staff API.
  expect((await page.request.get('/api/staff/applications')).status()).toBe(403)
})
