export interface Me {
  id: number
  email: string
  email_verified: boolean
  is_staff: boolean
  is_reviewer: boolean
}

export type ApplicationStatus = 'DRAFT' | 'IN_PROGRESS' | 'ACTION_REQUIRED' | 'MANUAL_REVIEW' | 'PASSED' | 'FAILED'
export type StepKey = 'profile' | 'consent' | 'document' | 'selfie' | 'right_to_work' | 'licence'
export type Route = 'share_code' | 'british_irish'
export type DocumentType = 'passport' | 'uk_licence' | 'id_card'

export interface LiveCheckState {
  state: 'not_started' | 'running' | 'needs_new_code' | 'done'
  message: string
}

export interface DriverApplication {
  id: string
  status: ApplicationStatus
  status_label: string
  outcome_message: string
  route: Route | null
  steps: { key: StepKey; label: string; done: boolean; editable: boolean }[]
  next_step: StepKey | null
  can_submit: boolean
  profile: { first_name: string; last_name: string; dob: string; phone: string }
  consent_given: boolean
  document: { type: DocumentType | null; has_front: boolean; has_back: boolean; needs_back: boolean }
  selfie_frames: number
  right_to_work: LiveCheckState
  licence: LiveCheckState & { licence_number: string; has_dqc_card: boolean }
  action: { steps: StepKey[]; message: string }
  submitted_at: string | null
  live_checks: { configured: boolean; sandbox: boolean }
  email_verified: boolean
  email_verification_required: boolean
}

export type CheckStatus = 'pending' | 'running' | 'pass' | 'fail' | 'unclear' | 'skipped'

export interface StaffRow {
  id: string
  email: string
  name: string
  status: ApplicationStatus
  status_label: string
  route: Route | null
  is_test: boolean
  submitted_at: string | null
  updated_at: string
}

export interface StaffList {
  results: StaffRow[]
  counts: Partial<Record<ApplicationStatus, number>>
}

export interface StaffCheck {
  type: string
  label: string
  status: CheckStatus
  reasons: string[]
  details: Record<string, unknown>
  provider: string
  simulated: boolean
  completed_at: string | null
}

export interface StaffEvidence {
  id: string
  kind: string
  label: string
  content_type: string
  url: string
  created_at: string
}

export interface StaffDetail extends StaffRow {
  profile: { first_name: string | null; last_name: string | null; dob: string | null; phone: string | null }
  document_type: DocumentType | null
  licence_number: string | null
  rtw_expires_at: string | null
  decided_at: string | null
  review: { decision: 'approve' | 'reject' | null; note: string; by: string | null; at: string | null }
  action: { steps: StepKey[]; message: string }
  checks: StaffCheck[]
  evidence: StaffEvidence[]
  audit: { at: string; actor: string; action: string; detail: Record<string, unknown> }[]
  reopenable_steps: { key: StepKey; label: string }[]
}
