import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'
import { z } from 'zod'

import { api, fieldError } from '../../api/client'
import { useDriverAction } from '../../api/hooks'
import type { DocumentType, DriverApplication, LiveCheckState } from '../../api/types'
import { FaceScan } from '../../components/FaceScan'
import { PhotoPicker } from '../../components/PhotoPicker'
import { Alert, Button, cx, Field, Spinner } from '../../components/ui'
import { checkCodeSchema, licenceNumberSchema, shareCodeSchema, ukMobileSchema } from '../../lib/validation'
import { StepPage, useGoNext } from './shell'

const post = (path: string, body: unknown, method = 'POST') => api<DriverApplication>(path, { method, body })

const ExternalLink = ({ href, children }: { href: string; children: React.ReactNode }) => (
  <a href={href} target="_blank" rel="noreferrer" className="font-semibold text-brand-700 underline">
    {children}
    <span className="sr-only"> (opens in a new tab)</span>
  </a>
)

// --- About you ----------------------------------------------------------------

const profileSchema = z.object({
  first_name: z.string().trim().min(1, 'Enter your first name as it appears on your ID.'),
  last_name: z.string().trim().min(1, 'Enter your last name as it appears on your ID.'),
  dob: z.string().min(1, 'Enter your date of birth.'),
  phone: ukMobileSchema,
  route: z.enum(['share_code', 'british_irish'], { error: 'Tell us if you are a British or Irish citizen.' }),
})
type ProfileForm = z.input<typeof profileSchema>

export function ProfileStep() {
  return (
    <StepPage step="profile" title="About you" intro="Enter your details exactly as they appear on your passport or ID card.">
      {(app) => <ProfileForm app={app} />}
    </StepPage>
  )
}

function ProfileForm({ app }: { app: DriverApplication }) {
  const goNext = useGoNext()
  const save = useDriverAction((body: z.output<typeof profileSchema>) => post('/api/driver/profile', body, 'PUT'))
  const form = useForm<ProfileForm, unknown, z.output<typeof profileSchema>>({
    resolver: zodResolver(profileSchema),
    defaultValues: { ...app.profile, route: app.route ?? undefined },
  })
  const { errors } = form.formState
  const serverError = (name: string) => fieldError(save.error, name)
  return (
    <form noValidate className="space-y-5" onSubmit={form.handleSubmit((v) => save.mutate(v, { onSuccess: goNext }))}>
      {save.error && <Alert tone="error">{save.error.message}</Alert>}
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="First name" autoComplete="given-name" error={errors.first_name?.message ?? serverError('first_name')} {...form.register('first_name')} />
        <Field label="Last name" autoComplete="family-name" error={errors.last_name?.message ?? serverError('last_name')} {...form.register('last_name')} />
      </div>
      <Field label="Date of birth" type="date" autoComplete="bday" error={errors.dob?.message ?? serverError('dob')} {...form.register('dob')} />
      <Field
        label="Mobile number"
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        hint="We'll only use this about your application."
        error={errors.phone?.message ?? serverError('phone')}
        {...form.register('phone')}
      />
      <fieldset>
        <legend className="text-sm font-semibold text-slate-800">Are you a British or Irish citizen?</legend>
        <p className="mt-1 text-sm text-slate-600">If you are not, you'll need a right to work share code from gov.uk.</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {[
            { value: 'british_irish', label: 'Yes', hint: 'I have a British or Irish passport' },
            { value: 'share_code', label: 'No', hint: 'I have an eVisa or other permission to work' },
          ].map((o) => (
            <label key={o.value} className="flex min-h-14 cursor-pointer items-start gap-3 rounded-xl border border-slate-300 p-4 has-[:checked]:border-brand-500 has-[:checked]:bg-brand-50">
              <input type="radio" value={o.value} className="mt-1 size-5 accent-brand-700" {...form.register('route')} />
              <span>
                <span className="block font-semibold">{o.label}</span>
                <span className="block text-sm text-slate-600">{o.hint}</span>
              </span>
            </label>
          ))}
        </div>
        {errors.route && <p className="mt-2 text-sm font-medium text-red-700">{errors.route.message}</p>}
      </fieldset>
      <Button type="submit" block loading={save.isPending}>
        Save and continue
      </Button>
    </form>
  )
}

// --- Consent ------------------------------------------------------------------

export function ConsentStep() {
  return (
    <StepPage step="consent" title="Before you start" intro="We need your agreement to check your details.">
      {(app) => <ConsentForm app={app} />}
    </StepPage>
  )
}

function ConsentForm({ app }: { app: DriverApplication }) {
  const goNext = useGoNext()
  const [data, setData] = useState(app.consent_given)
  const [dvla, setDvla] = useState(app.consent_given)
  const [touched, setTouched] = useState(false)
  const save = useDriverAction(() => post('/api/driver/consent', { data_consent: data, dvla_consent: dvla }))
  return (
    <div className="space-y-5">
      <div className="space-y-3 text-sm text-slate-700">
        <p>To decide if you can drive for us, we will:</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>take photos of your ID and your face, so our team can check they match</li>
          <li>check your right to work with the Home Office, if you use a share code</li>
          <li>check your driving licence with the DVLA</li>
        </ul>
        <p>Only our onboarding team sees your photos and results. Photos are encrypted and deleted when they're no longer needed.</p>
      </div>
      {save.error && <Alert tone="error">{save.error.message}</Alert>}
      {[
        { checked: data, set: setData, label: 'I agree to the checks above and to my photos being used to confirm my identity.' },
        { checked: dvla, set: setDvla, label: 'I agree to the DVLA sharing my driving licence details with you.' },
      ].map((c) => (
        <label key={c.label} className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-300 p-4">
          <input type="checkbox" checked={c.checked} onChange={(e) => c.set(e.target.checked)} className="mt-0.5 size-5 shrink-0 accent-brand-700" />
          <span className="text-sm text-slate-800">{c.label}</span>
        </label>
      ))}
      {touched && !(data && dvla) && <p className="text-sm font-medium text-red-700">You need to agree to both to carry on.</p>}
      <Button
        block
        loading={save.isPending}
        onClick={() => {
          setTouched(true)
          if (data && dvla) save.mutate(undefined, { onSuccess: goNext })
        }}
      >
        Agree and continue
      </Button>
    </div>
  )
}

// --- Photo ID -----------------------------------------------------------------

const DOCUMENTS: { value: DocumentType; label: string; back: boolean }[] = [
  { value: 'passport', label: 'Passport', back: false },
  { value: 'uk_licence', label: 'UK photocard driving licence', back: true },
  { value: 'id_card', label: 'EU or EEA national ID card', back: true },
]

export function DocumentStep() {
  return (
    <StepPage
      step="document"
      title="Photo ID"
      intro="Take a clear photo of your ID on a flat, dark surface. Make sure all four corners are in the photo and there's no glare."
    >
      {(app) => <DocumentForm app={app} />}
    </StepPage>
  )
}

function DocumentForm({ app }: { app: DriverApplication }) {
  const goNext = useGoNext()
  const [type, setType] = useState<DocumentType | null>(app.document.type)
  const [front, setFront] = useState<Blob | null>(null)
  const [back, setBack] = useState<Blob | null>(null)
  const [missing, setMissing] = useState(false)
  const needsBack = DOCUMENTS.find((d) => d.value === type)?.back ?? false
  const upload = useDriverAction(() => {
    const body = new FormData()
    body.append('document_type', type!)
    body.append('front', front!, 'front.jpg')
    if (needsBack && back) body.append('back', back, 'back.jpg')
    return post('/api/driver/identity/document', body)
  })

  function submit() {
    setMissing(true)
    if (type && front && (!needsBack || back)) upload.mutate(undefined, { onSuccess: goNext })
  }

  return (
    <div className="space-y-6">
      {app.document.has_front && <Alert tone="success">We have your ID photo. Take a new one only if you want to replace it.</Alert>}
      <fieldset>
        <legend className="text-sm font-semibold text-slate-800">Which ID are you using?</legend>
        <div className="mt-3 space-y-2">
          {DOCUMENTS.map((d) => (
            <label key={d.value} className="flex min-h-12 cursor-pointer items-center gap-3 rounded-xl border border-slate-300 px-4 has-[:checked]:border-brand-500 has-[:checked]:bg-brand-50">
              <input type="radio" name="document_type" checked={type === d.value} onChange={() => setType(d.value)} className="size-5 accent-brand-700" />
              <span className="font-medium">{d.label}</span>
            </label>
          ))}
        </div>
        {missing && !type && <p className="mt-2 text-sm font-medium text-red-700">Choose the ID you're using.</p>}
      </fieldset>
      {type && (
        <>
          <PhotoPicker
            label={type === 'passport' ? 'Photo page' : 'Front of the card'}
            hint={type === 'passport' ? 'The page with your photo and details.' : undefined}
            value={front}
            onChange={setFront}
            error={missing && !front ? 'Add a photo.' : fieldError(upload.error, 'front') ?? fieldError(upload.error, 'photo')}
          />
          {needsBack && (
            <PhotoPicker label="Back of the card" value={back} onChange={setBack} error={missing && !back ? 'Add a photo of the back.' : undefined} />
          )}
        </>
      )}
      {upload.error && !fieldError(upload.error, 'photo') && <Alert tone="error">{upload.error.message}</Alert>}
      <Button block loading={upload.isPending} onClick={submit}>
        Upload and continue
      </Button>
      {app.document.has_front && !front && (
        <Button block variant="ghost" onClick={() => goNext(app)}>
          Keep my current photo
        </Button>
      )}
    </div>
  )
}

// --- Face scan ------------------------------------------------------------------

export function SelfieStep() {
  return (
    <StepPage step="selfie" title="Face scan" intro="We'll use your front camera to check you're the person on your ID.">
      {(app) => <SelfieForm app={app} />}
    </StepPage>
  )
}

function SelfieForm({ app }: { app: DriverApplication }) {
  const goNext = useGoNext()
  const upload = useDriverAction((frames: Blob[]) => {
    const body = new FormData()
    frames.forEach((f, i) => body.append('frames', f, `frame-${i + 1}.jpg`))
    return post('/api/driver/identity/selfie', body)
  })
  return (
    <div className="space-y-5">
      {app.selfie_frames >= 3 && <Alert tone="success">Your face scan is done. Scan again only if you want to replace it.</Alert>}
      {upload.error && <Alert tone="error">{upload.error.message}</Alert>}
      <FaceScan busy={upload.isPending} onComplete={(frames) => upload.mutate(frames, { onSuccess: goNext })} />
      {app.selfie_frames >= 3 && (
        <Button block variant="ghost" onClick={() => goNext(app)}>
          Keep my current scan
        </Button>
      )}
    </div>
  )
}

// --- Live checks (share code, licence) -----------------------------------------------

function CheckRunning({ what }: { what: string }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl bg-brand-50 p-6 text-center text-brand-900" role="status">
      <Spinner className="size-8" />
      <p className="font-semibold">Checking with {what}…</p>
      <p className="text-sm">This usually takes under a minute. You can leave this page open.</p>
    </div>
  )
}

function CheckDone({ state, app, children }: { state: LiveCheckState; app: DriverApplication; children: React.ReactNode }) {
  const goNext = useGoNext()
  const [redo, setRedo] = useState(false)
  if (state.state !== 'done' || redo) return <>{children}</>
  return (
    <div className="space-y-4">
      <Alert tone="success">Thanks. This check is done.</Alert>
      <Button block onClick={() => goNext(app)}>
        Continue
      </Button>
      <Button block variant="ghost" onClick={() => setRedo(true)}>
        Enter a different code
      </Button>
    </div>
  )
}

function SandboxNote({ app, codes }: { app: DriverApplication; codes: string }) {
  if (!app.live_checks.sandbox) return null
  return <Alert tone="warning" title="Test mode">No real checks are made. Use {codes}.</Alert>
}

export function RightToWorkStep() {
  return (
    <StepPage
      step="right_to_work"
      title="Right to work"
      intro={
        <p>
          Get a share code at <ExternalLink href="https://www.gov.uk/prove-right-to-work">gov.uk/prove-right-to-work</ExternalLink>.
          Choose to prove your right to work. The code starts with W and lasts 90 days.
        </p>
      }
    >
      {(app) => <RightToWorkForm app={app} />}
    </StepPage>
  )
}

function RightToWorkForm({ app }: { app: DriverApplication }) {
  const schema = z.object({ share_code: shareCodeSchema(app.live_checks.sandbox) })
  const form = useForm<z.input<typeof schema>, unknown, z.output<typeof schema>>({ resolver: zodResolver(schema) })
  const check = useDriverAction((body: z.output<typeof schema>) => post('/api/driver/right-to-work', body))
  const state = app.right_to_work

  if (state.state === 'running') return <CheckRunning what="the Home Office" />
  return (
    <CheckDone state={state} app={app}>
      <form noValidate className="space-y-5" onSubmit={form.handleSubmit((v) => check.mutate(v))}>
        <SandboxNote app={app} codes="AA1 AA1 AA1 (accepted, for a person called Alex Test Sample) or CC3 CC3 CC3 (not found)" />
        {state.state === 'needs_new_code' && <Alert tone="warning" title="Enter your share code again">{state.message}</Alert>}
        {check.error && !fieldError(check.error, 'share_code') && <Alert tone="error">{check.error.message}</Alert>}
        <Field
          label="Share code"
          hint="For example W12 3AB C45"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          className="max-w-xs"
          error={form.formState.errors.share_code?.message ?? fieldError(check.error, 'share_code')}
          {...form.register('share_code')}
        />
        <p className="text-sm text-slate-600">We'll check it with the date of birth you gave us ({app.profile.dob}).</p>
        <Button type="submit" block loading={check.isPending}>
          Check my right to work
        </Button>
      </form>
    </CheckDone>
  )
}

export function LicenceStep() {
  return (
    <StepPage
      step="licence"
      title="Driving licence"
      intro={
        <p>
          Get a check code at <ExternalLink href="https://www.gov.uk/view-driving-licence">gov.uk/view-driving-licence</ExternalLink> by
          choosing "Share your licence information". The code works once and lasts 21 days.
        </p>
      }
    >
      {(app) => <LicenceForm app={app} />}
    </StepPage>
  )
}

const licenceSchema = z.object({ licence_number: licenceNumberSchema, check_code: checkCodeSchema })

function LicenceForm({ app }: { app: DriverApplication }) {
  const form = useForm<z.input<typeof licenceSchema>, unknown, z.output<typeof licenceSchema>>({ resolver: zodResolver(licenceSchema) })
  const check = useDriverAction((body: z.output<typeof licenceSchema>) => post('/api/driver/licence', body))
  const state = app.licence
  const { errors } = form.formState

  return (
    <div className="space-y-8">
      {state.state === 'running' ? (
        <CheckRunning what="the DVLA" />
      ) : (
        <CheckDone state={state} app={app}>
          <form noValidate className="space-y-5" onSubmit={form.handleSubmit((v) => check.mutate(v))}>
            <SandboxNote app={app} codes="licence number NOWAK803147T99AB with check code AAAA followed by any 4 characters (a clean car licence with no HGV entitlement, so the application won't be approved), CCCC… (6 points) or DDDD… (refused). Each code works once, so change the last 4 characters to try again" />
            {state.state === 'needs_new_code' && <Alert tone="warning" title="We need a new check code">{state.message}</Alert>}
            {check.error && !fieldError(check.error, 'licence_number') && !fieldError(check.error, 'check_code') && (
              <Alert tone="error">{check.error.message}</Alert>
            )}
            <Field
              label="Driving licence number"
              hint="16 characters, in section 5 of your photocard"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              error={errors.licence_number?.message ?? fieldError(check.error, 'licence_number')}
              {...form.register('licence_number')}
            />
            <Field
              label="DVLA check code"
              hint="8 letters and numbers, for example Hb Rh fp 7g. Capitals matter."
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              className="max-w-xs"
              error={errors.check_code?.message ?? fieldError(check.error, 'check_code')}
              {...form.register('check_code')}
            />
            <Button type="submit" block loading={check.isPending}>
              Check my licence
            </Button>
          </form>
        </CheckDone>
      )}
      <DqcUpload app={app} />
    </div>
  )
}

function DqcUpload({ app }: { app: DriverApplication }) {
  const [photo, setPhoto] = useState<Blob | null>(null)
  const upload = useDriverAction(() => {
    const body = new FormData()
    body.append('photo', photo!, 'dqc.jpg')
    return post('/api/driver/licence/dqc', body)
  })
  return (
    <section className="space-y-4 border-t border-slate-200 pt-6">
      <div>
        <h2 className="text-lg font-semibold">Driver CPC card (optional)</h2>
        <p className="mt-1 text-sm text-slate-600">
          The DVLA check doesn't show your Driver CPC. Add a photo of your driver qualification card to speed up your review.
        </p>
      </div>
      {app.licence.has_dqc_card && !photo ? (
        <Alert tone="success">We have your DQC card photo.</Alert>
      ) : (
        <>
          <PhotoPicker label="Front of your DQC card" value={photo} onChange={setPhoto} error={fieldError(upload.error, 'photo')} />
          {photo && (
            <Button block variant="secondary" loading={upload.isPending} onClick={() => upload.mutate(undefined, { onSuccess: () => setPhoto(null) })}>
              Upload DQC card
            </Button>
          )}
        </>
      )}
    </section>
  )
}

// --- Check and send ------------------------------------------------------------

export function ReviewStep() {
  return (
    <StepPage step="review" title="Check and send" intro="Make sure everything is right before you send your application.">
      {(app) => <ReviewForm app={app} />}
    </StepPage>
  )
}

function ReviewForm({ app }: { app: DriverApplication }) {
  const goNext = useGoNext()
  const [declared, setDeclared] = useState(false)
  const submit = useDriverAction(() => post('/api/driver/submit', undefined))
  return (
    <div className="space-y-6">
      <ul className="divide-y divide-slate-200 rounded-xl ring-1 ring-slate-200">
        {app.steps.map((s) => (
          <li key={s.key} className="flex min-h-14 items-center justify-between gap-3 px-4 py-3">
            <span className="flex items-center gap-3">
              <span
                className={cx(
                  'flex size-6 items-center justify-center rounded-full text-xs font-bold',
                  s.done ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-900',
                )}
                aria-hidden="true"
              >
                {s.done ? '✓' : '!'}
              </span>
              <span className="font-medium">
                {s.label}
                <span className="sr-only">{s.done ? ': done' : ': not done'}</span>
              </span>
            </span>
            {s.editable && (
              <Link
                to={`/apply/${s.key}`}
                aria-label={`${s.done ? 'Change' : 'Finish'} ${s.label}`}
                className="text-sm font-semibold text-brand-700 underline"
              >
                {s.done ? 'Change' : 'Finish'}
              </Link>
            )}
          </li>
        ))}
      </ul>
      {!app.can_submit ? (
        <Alert tone="warning">Finish the steps marked ! before you send your application.</Alert>
      ) : (
        <>
          <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-300 p-4">
            <input type="checkbox" checked={declared} onChange={(e) => setDeclared(e.target.checked)} className="mt-0.5 size-5 shrink-0 accent-brand-700" />
            <span className="text-sm">I confirm the information I've given is true and the photos are of me.</span>
          </label>
          {submit.error && <Alert tone="error">{submit.error.message}</Alert>}
          <Button block disabled={!declared} loading={submit.isPending} onClick={() => submit.mutate(undefined, { onSuccess: goNext })}>
            Send application
          </Button>
        </>
      )}
    </div>
  )
}
