import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { vi } from 'vitest'

import type { DriverApplication } from '../api/types'

export function application(overrides: Partial<DriverApplication> = {}): DriverApplication {
  return {
    id: 'app-1',
    status: 'DRAFT',
    status_label: 'In progress',
    outcome_message: '',
    route: 'share_code',
    steps: [
      { key: 'profile', label: 'About you', done: true, editable: true },
      { key: 'consent', label: 'Consent', done: false, editable: true },
      { key: 'document', label: 'Photo ID', done: false, editable: true },
      { key: 'selfie', label: 'Face scan', done: false, editable: true },
      { key: 'right_to_work', label: 'Right to work', done: false, editable: true },
      { key: 'licence', label: 'Driving licence', done: false, editable: true },
    ],
    next_step: 'consent',
    can_submit: false,
    profile: { first_name: 'Tomasz', last_name: 'Nowak', dob: '1987-03-14', phone: '07700900123' },
    consent_given: false,
    document: { type: null, has_front: false, has_back: false, needs_back: false },
    selfie_frames: 0,
    right_to_work: { state: 'not_started', message: '' },
    licence: { state: 'not_started', message: '', licence_number: '', has_dqc_card: false },
    action: { steps: [], message: '' },
    submitted_at: null,
    live_checks: { configured: true, sandbox: false },
    email_verified: true,
    email_verification_required: false,
    ...overrides,
  }
}

/** Mocks fetch: GET returns `app`, other calls go to `onWrite` (which returns the updated application). */
export function mockApi(app: DriverApplication, onWrite: (path: string, body: unknown) => unknown = () => app) {
  document.cookie = 'csrftoken=test-token'
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : init?.body
    const data = method === 'GET' ? app : onWrite(path, body)
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Every call that wasn't a GET: what the page tried to send. */
export function writes(fetchMock: ReturnType<typeof mockApi>) {
  return fetchMock.mock.calls.filter(([, init]) => init?.method && init.method !== 'GET').map(([path]) => path)
}

export function renderAt(path: string, element: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={path} element={element} />
          <Route path="*" element={<p>Navigated away</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
