import type { ApplicationStatus, CheckStatus } from '../../api/types'
import { Badge } from '../../components/ui'

const STATUS_TONES: Record<ApplicationStatus, 'slate' | 'green' | 'red' | 'amber' | 'blue'> = {
  DRAFT: 'slate',
  IN_PROGRESS: 'blue',
  ACTION_REQUIRED: 'amber',
  MANUAL_REVIEW: 'blue',
  PASSED: 'green',
  FAILED: 'red',
}

export function StatusBadge({ status, label }: { status: ApplicationStatus; label: string }) {
  return <Badge tone={STATUS_TONES[status]}>{label}</Badge>
}

const CHECK_TONES: Record<CheckStatus, 'slate' | 'green' | 'red' | 'amber' | 'blue'> = {
  pending: 'slate',
  running: 'blue',
  pass: 'green',
  fail: 'red',
  unclear: 'amber',
  skipped: 'slate',
}

const CHECK_LABELS: Record<CheckStatus, string> = {
  pending: 'Not run',
  running: 'Running',
  pass: 'Pass',
  fail: 'Fail',
  unclear: 'Needs a person',
  skipped: 'Skipped',
}

export function CheckBadge({ status }: { status: CheckStatus }) {
  return <Badge tone={CHECK_TONES[status]}>{CHECK_LABELS[status]}</Badge>
}
