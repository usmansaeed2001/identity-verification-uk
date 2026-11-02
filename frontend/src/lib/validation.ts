/** Mirrors backend/onboarding/validation.py so drivers see typos before anything is sent. */
import { z } from 'zod'

export const normaliseShareCode = (raw: string) => raw.replace(/[\s-]/g, '').toUpperCase()
export const normaliseLicence = (raw: string) => raw.replace(/\s/g, '').toUpperCase()

export function shareCodeSchema(sandbox: boolean) {
  return z
    .string()
    .transform(normaliseShareCode)
    .refine((v) => v.length === 9, 'A share code has 9 characters, for example W12 3AB C45.')
    .refine((v) => sandbox || v.startsWith('W'), "Right to work share codes start with W. Make one at gov.uk/prove-right-to-work.")
    .refine((v) => /^[A-Z0-9]{9}$/.test(v), 'A share code can only contain letters and numbers.')
}

export const licenceNumberSchema = z
  .string()
  .transform(normaliseLicence)
  .refine((v) => v.length === 16, 'A UK driving licence number has 16 characters (section 5 of the photocard).')
  .refine(
    (v) => /^[A-Z9]{5}\d{6}[A-Z9]{2}\d[A-Z0-9]{2}$/.test(v),
    "That doesn't look like a UK driving licence number. Check section 5 of the photocard.",
  )

export const checkCodeSchema = z
  .string()
  .transform((v) => v.replace(/\s/g, ''))
  .refine((v) => /^[A-Za-z0-9]{8}$/.test(v), 'A DVLA check code has 8 letters and numbers, for example Hb Rh fp 7g.')

export const ukMobileSchema = z
  .string()
  .transform((v) => v.replace(/[\s()-]/g, ''))
  .refine((v) => /^(\+44|0)7\d{9}$/.test(v), 'Enter a UK mobile number, for example 07700 900123.')

export const passwordSchema = z.string().min(10, 'Use at least 10 characters.')
