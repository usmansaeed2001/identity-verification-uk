import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { application, mockApi, renderAt, writes } from '../../test/render'
import { ConsentStep, ProfileStep, ReviewStep, RightToWorkStep } from './steps'

afterEach(() => vi.unstubAllGlobals())

describe('profile step', () => {
  it('checks the mobile number and citizenship before saving', async () => {
    const fetchMock = mockApi(application({ profile: { first_name: '', last_name: '', dob: '', phone: '' }, route: null }))
    renderAt('/apply/profile', <ProfileStep />)
    await userEvent.type(await screen.findByLabelText('First name'), 'Tomasz')
    await userEvent.type(screen.getByLabelText('Last name'), 'Nowak')
    await userEvent.type(screen.getByLabelText('Mobile number', { exact: false }), '020 7946 0000')
    await userEvent.click(screen.getByRole('button', { name: 'Save and continue' }))

    expect(await screen.findByText(/Enter a UK mobile number/)).toBeInTheDocument()
    expect(screen.getByText(/British or Irish citizen\./)).toBeInTheDocument()
    expect(writes(fetchMock)).toEqual([])
  })
})

describe('consent step', () => {
  it('needs both agreements', async () => {
    const fetchMock = mockApi(application(), () => application({ consent_given: true, next_step: 'document' }))
    renderAt('/apply/consent', <ConsentStep />)
    await userEvent.click(await screen.findByRole('checkbox', { name: /checks above/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Agree and continue' }))
    expect(screen.getByText('You need to agree to both to carry on.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('checkbox', { name: /DVLA/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Agree and continue' }))
    expect(await screen.findByText('Navigated away')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/driver/consent', expect.objectContaining({ method: 'POST' }))
  })
})

describe('right to work step', () => {
  it('shows why gov.uk refused the last code', async () => {
    mockApi(application({ right_to_work: { state: 'needs_new_code', message: 'The Home Office has no record for that share code.' } }))
    renderAt('/apply/right_to_work', <RightToWorkStep />)
    expect(await screen.findByText('The Home Office has no record for that share code.')).toBeInTheDocument()
  })

  it('shows progress while the check runs', async () => {
    mockApi(application({ right_to_work: { state: 'running', message: '' } }))
    renderAt('/apply/right_to_work', <RightToWorkStep />)
    expect(await screen.findByText('Checking with the Home Office…')).toBeInTheDocument()
  })

  it('refuses a share code that is not for work', async () => {
    const fetchMock = mockApi(application())
    renderAt('/apply/right_to_work', <RightToWorkStep />)
    await userEvent.type(await screen.findByLabelText('Share code', { exact: false }), 'R12 3AB C45')
    await userEvent.click(screen.getByRole('button', { name: 'Check my right to work' }))
    expect(await screen.findByText(/start with W/)).toBeInTheDocument()
    expect(writes(fetchMock)).toEqual([])
  })

  it('tells testers which codes to use with the sandbox key', async () => {
    mockApi(application({ live_checks: { configured: true, sandbox: true } }))
    renderAt('/apply/right_to_work', <RightToWorkStep />)
    expect(await screen.findByText(/AA1 AA1 AA1/)).toBeInTheDocument()
  })
})

describe('check and send', () => {
  it('needs the declaration before sending', async () => {
    const done = application().steps.map((s) => ({ ...s, done: true }))
    mockApi(application({ steps: done, next_step: null, can_submit: true }), () => application({ status: 'MANUAL_REVIEW' }))
    renderAt('/apply/review', <ReviewStep />)
    const send = await screen.findByRole('button', { name: 'Send application' })
    expect(send).toBeDisabled()
    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.click(send)
    expect(await screen.findByText('Navigated away')).toBeInTheDocument()
  })

  it('lists unfinished steps', async () => {
    mockApi(application())
    renderAt('/apply/review', <ReviewStep />)
    expect(await screen.findByText(/Finish the steps marked/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Finish Consent/ })).toHaveAttribute('href', '/apply/consent')
  })
})
