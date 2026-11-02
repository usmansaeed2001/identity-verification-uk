import { useMutation } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Link, Navigate, useNavigate } from 'react-router'

import { api } from '../../api/client'
import { useApplication } from '../../api/hooks'
import type { DriverApplication, StepKey } from '../../api/types'
import { Layout } from '../../components/Layout'
import { Alert, Button, Card, cx, PageLoader } from '../../components/ui'

export const SUBMITTED = ['IN_PROGRESS', 'MANUAL_REVIEW', 'PASSED', 'FAILED']

export function nextPath(app: DriverApplication): string {
  if (SUBMITTED.includes(app.status)) return '/apply/status'
  return `/apply/${app.next_step ?? 'review'}`
}

/** After a step is saved, go to the first unfinished step (or the review page). */
export function useGoNext() {
  const navigate = useNavigate()
  return (app: DriverApplication) => navigate(nextPath(app))
}

function Progress({ app, current }: { app: DriverApplication; current: StepKey | 'review' }) {
  const index = current === 'review' ? app.steps.length : app.steps.findIndex((s) => s.key === current)
  const label = current === 'review' ? 'Check and send' : app.steps[index]?.label
  return (
    <nav aria-label="Application progress" className="mb-6">
      <p className="text-sm font-medium text-slate-600">
        {current === 'review' ? 'Last step' : `Step ${index + 1} of ${app.steps.length}`} · <span className="text-slate-900">{label}</span>
      </p>
      <ol className="mt-3 flex gap-1.5">
        {app.steps.map((step, i) => (
          <li key={step.key} className="flex-1">
            <Link
              to={`/apply/${step.key}`}
              aria-label={`${step.label}${step.done ? ' (done)' : ''}`}
              aria-current={step.key === current ? 'step' : undefined}
              className={cx(
                'block h-2 rounded-full',
                step.key === current ? 'bg-brand-700' : step.done ? 'bg-brand-500/60' : i < index ? 'bg-amber-400' : 'bg-slate-200',
              )}
            />
          </li>
        ))}
      </ol>
    </nav>
  )
}

function EmailBanner({ app }: { app: DriverApplication }) {
  const resend = useMutation({ mutationFn: () => api('/api/auth/verify-email/resend', { method: 'POST' }) })
  if (app.email_verified || !app.email_verification_required) return null
  return (
    <div className="mb-6">
      <Alert tone="warning" title="Confirm your email address">
        We sent you a link. You need to confirm your email before we can run the right to work and licence checks.{' '}
        <button type="button" className="font-semibold underline" onClick={() => resend.mutate()} disabled={resend.isPending}>
          {resend.isSuccess ? 'Sent again' : 'Send it again'}
        </button>
      </Alert>
    </div>
  )
}

/** Wraps each step: loads the application, shows progress, and guards steps that can't be changed. */
export function StepPage({
  step,
  title,
  intro,
  children,
}: {
  step: StepKey | 'review'
  title: string
  intro?: ReactNode
  children: (app: DriverApplication) => ReactNode
}) {
  const { data: app, error, isLoading } = useApplication()
  const goNext = useGoNext()
  if (isLoading) return <Layout><PageLoader /></Layout>
  if (error || !app) return <Layout><Alert tone="error">{error?.message ?? 'Something went wrong.'}</Alert></Layout>
  if (SUBMITTED.includes(app.status)) return <Navigate to="/apply/status" replace />
  const info = app.steps.find((s) => s.key === step)
  if (step !== 'review' && !info) return <Navigate to={nextPath(app)} replace />

  return (
    <Layout>
      <Progress app={app} current={step} />
      <EmailBanner app={app} />
      {app.status === 'ACTION_REQUIRED' && app.action.message && (
        <div className="mb-6">
          <Alert tone="warning" title="Our team needs you to update your application">
            {app.action.message}
          </Alert>
        </div>
      )}
      <Card>
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        {intro && <div className="mt-2 space-y-2 text-slate-600">{intro}</div>}
        <div className="mt-6">
          {info && !info.editable ? (
            <div className="space-y-5">
              <Alert tone="info">{info.done ? 'This step is done.' : "You can't change this step now."}</Alert>
              <Button block onClick={() => goNext(app)}>
                Continue
              </Button>
            </div>
          ) : (
            children(app)
          )}
        </div>
      </Card>
    </Layout>
  )
}

export function ApplyIndex() {
  const { data: app, error, isLoading } = useApplication()
  if (isLoading) return <Layout><PageLoader /></Layout>
  if (error || !app) return <Layout><Alert tone="error">{error?.message ?? 'Something went wrong.'}</Alert></Layout>
  return <Navigate to={nextPath(app)} replace />
}

const OUTCOMES = {
  MANUAL_REVIEW: { title: 'Application sent', tone: 'text-brand-700 bg-brand-50', icon: 'M12 8v4l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z' },
  IN_PROGRESS: { title: 'Application sent', tone: 'text-brand-700 bg-brand-50', icon: 'M12 8v4l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z' },
  PASSED: { title: "You're approved", tone: 'text-emerald-700 bg-emerald-50', icon: 'm5 13 4 4L19 7' },
  FAILED: { title: "We couldn't approve your application", tone: 'text-red-700 bg-red-50', icon: 'M6 18 18 6M6 6l12 12' },
} as const

export function StatusPage() {
  const { data: app, isLoading } = useApplication()
  if (isLoading || !app) return <Layout><PageLoader /></Layout>
  if (!SUBMITTED.includes(app.status)) return <Navigate to={nextPath(app)} replace />
  const outcome = OUTCOMES[app.status as keyof typeof OUTCOMES]
  return (
    <Layout>
      <Card className="text-center">
        <div className={cx('mx-auto flex size-16 items-center justify-center rounded-full', outcome.tone)}>
          <svg viewBox="0 0 24 24" className="size-8" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d={outcome.icon} />
          </svg>
        </div>
        <h1 className="mt-4 text-2xl font-bold">{outcome.title}</h1>
        <p className="mt-2 text-slate-600">{app.outcome_message}</p>
        {app.submitted_at && (
          <p className="mt-4 text-sm text-slate-500">
            Sent on {new Date(app.submitted_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}
          </p>
        )}
      </Card>
    </Layout>
  )
}
