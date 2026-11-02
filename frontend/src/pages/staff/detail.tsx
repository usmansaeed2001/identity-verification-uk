import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { api } from '../../api/client'
import { useStaffAction, useStaffDetail } from '../../api/hooks'
import type { StaffCheck, StaffDetail, StaffEvidence, StepKey } from '../../api/types'
import { Layout } from '../../components/Layout'
import { Alert, Badge, Button, Card, cx, PageLoader } from '../../components/ui'
import { CheckBadge, StatusBadge } from './common'

const formatDateTime = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

const humanise = (key: string) => key.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.length ? value.map(formatValue).join(', ') : '—'
  if (typeof value === 'object') return Object.entries(value).map(([k, v]) => `${humanise(k)}: ${formatValue(v)}`).join('; ')
  return String(value)
}

const HIDDEN_DETAILS = new Set(['simulated', 'provider'])

export function StaffDetailPage() {
  const { id = '' } = useParams()
  const { data, error, isLoading } = useStaffDetail(id)
  return (
    <Layout wide>
      <Link to="/staff" className="text-sm font-semibold text-brand-700 underline">
        ← All applications
      </Link>
      {isLoading && <PageLoader />}
      {error && <div className="mt-4"><Alert tone="error">{error.message}</Alert></div>}
      {data && <Detail app={data} />}
    </Layout>
  )
}

function Detail({ app }: { app: StaffDetail }) {
  const simulated = app.checks.some((c) => c.simulated)
  return (
    <div className="mt-4 space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">{app.name || 'No name yet'}</h1>
          <p className="text-slate-600">{app.email}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge status={app.status} label={app.status_label} />
          {app.is_test && <Badge tone="purple">Test data (sandbox key)</Badge>}
          {simulated && <Badge tone="amber">Identity checks simulated</Badge>}
        </div>
      </header>

      {simulated && app.status === 'MANUAL_REVIEW' && (
        <Alert tone="warning" title="The face match is simulated">
          Nothing compared these photos automatically. Check that the selfies, the photo ID and the Home Office photo show the same
          person before you approve.
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="min-w-0 space-y-6">
          <Photos evidence={app.evidence} />
          <Checks checks={app.checks} />
          <Documents evidence={app.evidence} />
          <Audit app={app} />
        </div>
        <aside className="space-y-6 lg:sticky lg:top-4 lg:self-start">
          <Decision app={app} />
          <Profile app={app} />
        </aside>
      </div>
    </div>
  )
}

const PHOTO_GROUPS: { title: string; kinds: string[] }[] = [
  { title: 'Face scan', kinds: ['selfie'] },
  { title: 'Photo ID', kinds: ['id_front', 'id_back'] },
  { title: 'Home Office photo', kinds: ['home_office_photo'] },
  { title: 'Driver CPC card', kinds: ['dqc_card'] },
]

function Photos({ evidence }: { evidence: StaffEvidence[] }) {
  const groups = PHOTO_GROUPS.map((g) => ({ ...g, items: evidence.filter((e) => g.kinds.includes(e.kind)) })).filter((g) => g.items.length)
  return (
    <Card className="!p-4 sm:!p-6">
      <h2 className="text-lg font-semibold">Compare the photos</h2>
      {groups.length === 0 ? (
        <p className="mt-2 text-sm text-slate-600">No photos yet.</p>
      ) : (
        <div className="mt-4 grid grid-cols-2 gap-4 xl:grid-cols-4">
          {groups.map((g) => (
            <figure key={g.title} className={cx('space-y-2', g.kinds[0] === 'selfie' && 'col-span-2')}>
              <figcaption className="text-sm font-semibold text-slate-700">{g.title}</figcaption>
              <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${Math.min(g.items.length, 3)}, minmax(0, 1fr))` }}>
                {g.items.map((e) => (
                  <a key={e.id} href={e.url} target="_blank" rel="noreferrer" className="group block overflow-hidden rounded-xl bg-slate-100 ring-1 ring-slate-200">
                    <img
                      src={e.url}
                      alt={e.label}
                      loading="lazy"
                      className={cx(
                        'aspect-[3/4] w-full transition group-hover:scale-105',
                        // Faces fill the frame; documents are shown whole so no detail is cropped off.
                        e.kind === 'selfie' || e.kind === 'home_office_photo' ? 'object-cover' : 'object-contain',
                      )}
                    />
                    <span className="sr-only">Open {e.label} full size</span>
                  </a>
                ))}
              </div>
            </figure>
          ))}
        </div>
      )}
    </Card>
  )
}

function Checks({ checks }: { checks: StaffCheck[] }) {
  return (
    <Card className="!p-4 sm:!p-6">
      <h2 className="text-lg font-semibold">Checks</h2>
      {checks.length === 0 && <p className="mt-2 text-sm text-slate-600">No checks have run yet.</p>}
      <ul className="mt-4 divide-y divide-slate-100">
        {checks.map((c) => {
          const details = Object.entries(c.details).filter(([k]) => !HIDDEN_DETAILS.has(k))
          return (
            <li key={c.type} className="py-4 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-semibold">{c.label}</h3>
                <CheckBadge status={c.status} />
                {c.simulated && <Badge tone="amber">Simulated</Badge>}
              </div>
              {c.reasons.length > 0 && (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {c.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              )}
              {details.length > 0 && (
                <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                  {details.map(([k, v]) => (
                    <div key={k} className="flex gap-2">
                      <dt className="shrink-0 text-slate-500">{humanise(k)}:</dt>
                      <dd className="min-w-0 break-words text-slate-800">{formatValue(v)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

function Documents({ evidence }: { evidence: StaffEvidence[] }) {
  const pdfs = evidence.filter((e) => e.content_type === 'application/pdf')
  if (!pdfs.length) return null
  return (
    <Card className="!p-4 sm:!p-6">
      <h2 className="text-lg font-semibold">Official records</h2>
      <ul className="mt-3 space-y-2">
        {pdfs.map((e) => (
          <li key={e.id}>
            <a href={e.url} target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center gap-2 font-semibold text-brand-700 underline">
              {e.label} (PDF)
            </a>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function Audit({ app }: { app: StaffDetail }) {
  return (
    <Card className="!p-4 sm:!p-6">
      <details>
        <summary className="cursor-pointer text-lg font-semibold">Audit trail ({app.audit.length})</summary>
        <ol className="mt-4 space-y-2 text-sm">
          {[...app.audit].reverse().map((a, i) => (
            <li key={i} className="grid gap-1 sm:grid-cols-[11rem_1fr]">
              <span className="text-slate-500">{formatDateTime(a.at)}</span>
              <span>
                <span className="font-medium">{humanise(a.action)}</span> <span className="text-slate-500">by {a.actor}</span>
                {Object.keys(a.detail).length > 0 && <span className="block text-slate-600">{formatValue(a.detail)}</span>}
              </span>
            </li>
          ))}
        </ol>
      </details>
    </Card>
  )
}

function Profile({ app }: { app: StaffDetail }) {
  const rows: [string, string | null][] = [
    ['First name', app.profile.first_name],
    ['Last name', app.profile.last_name],
    ['Date of birth', app.profile.dob],
    ['Mobile', app.profile.phone],
    ['Route', app.route === 'british_irish' ? 'British or Irish citizen' : app.route === 'share_code' ? 'Share code' : null],
    ['ID used', app.document_type ? humanise(app.document_type) : null],
    ['Licence number', app.licence_number],
    ['Right to work until', app.rtw_expires_at],
    ['Sent', formatDateTime(app.submitted_at)],
  ]
  return (
    <Card className="!p-4 sm:!p-6">
      <h2 className="text-lg font-semibold">Driver details</h2>
      <dl className="mt-3 space-y-2 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4">
            <dt className="text-slate-500">{k}</dt>
            <dd className="text-right font-medium break-all">{v || '—'}</dd>
          </div>
        ))}
      </dl>
    </Card>
  )
}

function Decision({ app }: { app: StaffDetail }) {
  const [note, setNote] = useState('')
  const [noteMissing, setNoteMissing] = useState(false)
  const [steps, setSteps] = useState<StepKey[]>([])
  const [message, setMessage] = useState('')
  const [askMissing, setAskMissing] = useState(false)
  const review = useStaffAction(app.id, (decision: 'approve' | 'reject') =>
    api<StaffDetail>(`/api/staff/applications/${app.id}/review`, { method: 'POST', body: { decision, note } }),
  )
  const ask = useStaffAction(app.id, () =>
    api<StaffDetail>(`/api/staff/applications/${app.id}/request-action`, { method: 'POST', body: { steps, message } }),
  )

  if (app.status !== 'MANUAL_REVIEW') {
    return (
      <Card className="!p-4 sm:!p-6">
        <h2 className="text-lg font-semibold">Outcome</h2>
        {app.review.decision ? (
          <div className="mt-3 space-y-1 text-sm">
            <p>
              <span className="font-semibold">{app.review.decision === 'approve' ? 'Approved' : 'Rejected'}</span> by {app.review.by} on{' '}
              {formatDateTime(app.review.at)}
            </p>
            <p className="whitespace-pre-line text-slate-700">{app.review.note}</p>
          </div>
        ) : app.status === 'ACTION_REQUIRED' ? (
          <p className="mt-3 text-sm text-slate-700">
            Waiting for the driver to update: <span className="font-semibold">{app.action.steps.map(humanise).join(', ')}</span>.
            <span className="mt-1 block whitespace-pre-line text-slate-600">“{app.action.message}”</span>
          </p>
        ) : (
          <p className="mt-3 text-sm text-slate-600">
            {app.status === 'FAILED' ? 'A check failed, so this application was not approved.' : 'The driver hasn’t sent this application yet.'}
          </p>
        )}
      </Card>
    )
  }

  const decide = (decision: 'approve' | 'reject') => {
    setNoteMissing(!note.trim())
    if (note.trim()) review.mutate(decision)
  }

  return (
    <Card className="!p-4 sm:!p-6">
      <h2 className="text-lg font-semibold">Your decision</h2>
      <div className="mt-3 space-y-3">
        <label htmlFor="note" className="block text-sm font-semibold">
          Note for the record
        </label>
        <textarea
          id="note"
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="For example: Selfie matches ID and Home Office photo. DQC valid until 2028."
          aria-invalid={noteMissing || undefined}
          className={cx('block w-full rounded-xl border bg-white px-3 py-2 text-sm', noteMissing ? 'border-red-600' : 'border-slate-300')}
        />
        {noteMissing && <p className="text-sm font-medium text-red-700">Add a note explaining your decision.</p>}
        {review.error && <Alert tone="error">{review.error.message}</Alert>}
        <div className="grid grid-cols-2 gap-2">
          <Button loading={review.isPending && review.variables === 'approve'} disabled={review.isPending} onClick={() => decide('approve')}>
            Approve
          </Button>
          <Button variant="danger" loading={review.isPending && review.variables === 'reject'} disabled={review.isPending} onClick={() => decide('reject')}>
            Reject
          </Button>
        </div>
      </div>

      <details className="mt-6 border-t border-slate-200 pt-4">
        <summary className="cursor-pointer font-semibold text-brand-800">Ask the driver for something</summary>
        <fieldset className="mt-3 space-y-2">
          <legend className="text-sm text-slate-600">What should they redo?</legend>
          {app.reopenable_steps.map((s) => (
            <label key={s.key} className="flex min-h-10 items-center gap-3 text-sm">
              <input
                type="checkbox"
                checked={steps.includes(s.key)}
                onChange={(e) => setSteps(e.target.checked ? [...steps, s.key] : steps.filter((k) => k !== s.key))}
                className="size-5 accent-brand-700"
              />
              {s.label}
            </label>
          ))}
        </fieldset>
        <label htmlFor="message" className="mt-3 block text-sm font-semibold">
          Message to the driver
        </label>
        <textarea
          id="message"
          rows={3}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="For example: Your ID photo is blurry. Please take it again in good light."
          className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm"
        />
        {askMissing && (!steps.length || !message.trim()) && (
          <p className="mt-2 text-sm font-medium text-red-700">Choose at least one step and write a message.</p>
        )}
        {ask.error && <div className="mt-2"><Alert tone="error">{ask.error.message}</Alert></div>}
        <Button
          block
          variant="secondary"
          className="mt-3"
          loading={ask.isPending}
          onClick={() => {
            setAskMissing(true)
            if (steps.length && message.trim()) ask.mutate(undefined)
          }}
        >
          Send to driver
        </Button>
      </details>
    </Card>
  )
}
