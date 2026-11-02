import { useEffect, useId, useMemo, useState } from 'react'

import { compressImage } from '../lib/image'
import { cx, Spinner } from './ui'

function useObjectUrl(blob: Blob | null) {
  const url = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob])
  useEffect(() => () => void (url && URL.revokeObjectURL(url)), [url])
  return url
}

const buttonClass =
  'flex min-h-12 flex-1 cursor-pointer items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold ring-1 ring-inset focus-within:outline focus-within:outline-3 focus-within:outline-brand-500'

/** Take a photo with the phone's camera app, or pick one from files. The photo is shrunk before upload. */
export function PhotoPicker({
  label,
  hint,
  value,
  onChange,
  error,
}: {
  label: string
  hint?: string
  value: Blob | null
  onChange: (blob: Blob | null) => void
  error?: string
}) {
  const id = useId()
  const preview = useObjectUrl(value)
  const [busy, setBusy] = useState(false)
  const [readError, setReadError] = useState<string>()

  async function handle(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setReadError(undefined)
    setBusy(true)
    try {
      onChange(await compressImage(file))
    } catch {
      setReadError("We couldn't read that photo. Try taking it again.")
    } finally {
      setBusy(false)
    }
  }

  const message = readError ?? error
  return (
    <fieldset className="space-y-3">
      <legend className="text-sm font-semibold text-slate-800">{label}</legend>
      {hint && <p className="text-sm text-slate-600">{hint}</p>}
      <div
        className={cx(
          'flex aspect-[1.586] w-full items-center justify-center overflow-hidden rounded-xl border-2 border-dashed bg-slate-100',
          message ? 'border-red-500' : 'border-slate-300',
        )}
      >
        {busy ? (
          <Spinner className="size-8 text-brand-700" />
        ) : preview ? (
          <img src={preview} alt={`${label} preview`} className="h-full w-full object-contain" />
        ) : (
          <svg viewBox="0 0 48 32" className="w-24 text-slate-400" aria-hidden="true">
            <rect x="1" y="1" width="46" height="30" rx="4" fill="none" stroke="currentColor" strokeWidth="2" />
            <circle cx="14" cy="14" r="5" fill="currentColor" />
            <rect x="24" y="10" width="17" height="3" rx="1.5" fill="currentColor" />
            <rect x="24" y="17" width="12" height="3" rx="1.5" fill="currentColor" />
          </svg>
        )}
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <label htmlFor={`${id}-camera`} className={cx(buttonClass, 'bg-brand-700 text-white ring-brand-700')}>
          {preview ? 'Retake photo' : 'Take photo'}
          <input id={`${id}-camera`} type="file" accept="image/*" capture="environment" className="sr-only" onChange={handle} />
        </label>
        <label htmlFor={`${id}-file`} className={cx(buttonClass, 'bg-white text-brand-800 ring-slate-300')}>
          Choose a file
          <input id={`${id}-file`} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={handle} />
        </label>
      </div>
      {message && <p className="text-sm font-medium text-red-700">{message}</p>}
    </fieldset>
  )
}
