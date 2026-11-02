import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { useStaffList } from '../../api/hooks'
import type { ApplicationStatus } from '../../api/types'
import { Layout } from '../../components/Layout'
import { Alert, Badge, cx, PageLoader } from '../../components/ui'
import { StatusBadge } from './common'

const TABS: { status: ApplicationStatus | ''; label: string }[] = [
  { status: 'MANUAL_REVIEW', label: 'To review' },
  { status: 'ACTION_REQUIRED', label: 'Waiting for driver' },
  { status: 'DRAFT', label: 'In progress' },
  { status: 'PASSED', label: 'Approved' },
  { status: 'FAILED', label: 'Not approved' },
  { status: '', label: 'All' },
]

const formatDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'

export function StaffListPage() {
  const [params, setParams] = useSearchParams()
  const status = params.get('status') ?? 'MANUAL_REVIEW'
  const [q, setQ] = useState(params.get('q') ?? '')
  const { data, error, isLoading } = useStaffList({ status, q: params.get('q') ?? '' })

  const update = (next: Record<string, string>) => setParams({ status, q: params.get('q') ?? '', ...next }, { replace: true })

  return (
    <Layout wide>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Driver applications</h1>
          <p className="mt-1 text-slate-600">Check the evidence, then approve, reject or ask the driver for more.</p>
        </div>
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault()
            update({ q })
          }}
          className="flex gap-2"
        >
          <label htmlFor="search" className="sr-only">
            Search by name or email
          </label>
          <input
            id="search"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search name or email"
            className="min-h-11 w-full rounded-xl border border-slate-300 bg-white px-4 sm:w-72"
          />
          <button type="submit" className="min-h-11 rounded-xl bg-brand-700 px-4 font-semibold text-white">
            Search
          </button>
        </form>
      </div>

      <div className="-mx-4 mt-6 overflow-x-auto px-4">
        <div role="tablist" aria-label="Filter by status" className="flex min-w-max gap-2">
          {TABS.map((t) => {
            const count = t.status ? data?.counts[t.status] : undefined
            const active = status === t.status
            return (
              <button
                key={t.label}
                role="tab"
                aria-selected={active}
                onClick={() => update({ status: t.status })}
                className={cx(
                  'min-h-11 rounded-full px-4 text-sm font-semibold',
                  active ? 'bg-brand-800 text-white' : 'bg-white text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50',
                )}
              >
                {t.label}
                {count ? <span className={cx('ml-2 rounded-full px-2 text-xs', active ? 'bg-white/20' : 'bg-slate-100')}>{count}</span> : null}
              </button>
            )
          })}
        </div>
      </div>

      <div className="mt-6">
        {isLoading && <PageLoader />}
        {error && <Alert tone="error">{error.message}</Alert>}
        {data && data.results.length === 0 && (
          <div className="rounded-2xl bg-white p-10 text-center text-slate-600 ring-1 ring-slate-200">No applications here.</div>
        )}
        {data && data.results.length > 0 && (
          <>
            {/* Cards on phones */}
            <ul className="space-y-3 md:hidden">
              {data.results.map((row) => (
                <li key={row.id}>
                  <Link to={`/staff/applications/${row.id}`} className="block rounded-2xl bg-white p-4 ring-1 ring-slate-200 hover:ring-brand-500">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate font-semibold">{row.name || 'No name yet'}</p>
                        <p className="truncate text-sm text-slate-600">{row.email}</p>
                      </div>
                      <StatusBadge status={row.status} label={row.status_label} />
                    </div>
                    <p className="mt-2 text-xs text-slate-500">
                      Sent {formatDate(row.submitted_at)} {row.is_test && <Badge tone="purple">Test</Badge>}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
            {/* Table on larger screens */}
            <div className="hidden overflow-hidden rounded-2xl bg-white ring-1 ring-slate-200 md:block">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Driver</th>
                    <th className="px-4 py-3 font-semibold">Route</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold">Sent</th>
                    <th className="px-4 py-3 font-semibold">Updated</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.results.map((row) => (
                    <tr key={row.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <Link to={`/staff/applications/${row.id}`} className="font-semibold text-brand-700 hover:underline">
                          {row.name || 'No name yet'}
                        </Link>
                        <div className="text-slate-500">{row.email}</div>
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {row.route === 'british_irish' ? 'British/Irish' : row.route === 'share_code' ? 'Share code' : '—'}
                        {row.is_test && <span className="ml-2"><Badge tone="purple">Test</Badge></span>}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={row.status} label={row.status_label} />
                      </td>
                      <td className="px-4 py-3 text-slate-600">{formatDate(row.submitted_at)}</td>
                      <td className="px-4 py-3 text-slate-600">{formatDate(row.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </Layout>
  )
}
