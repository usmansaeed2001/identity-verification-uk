import { describe, expect, it } from 'vitest'

import { checkCodeSchema, licenceNumberSchema, shareCodeSchema, ukMobileSchema } from './validation'

describe('share code', () => {
  it('normalises spaces, dashes and case', () => {
    expect(shareCodeSchema(false).parse('w12-3ab c45')).toBe('W123ABC45')
  })

  it('needs a W unless the sandbox key is in use', () => {
    expect(shareCodeSchema(false).safeParse('AA1AA1AA1').success).toBe(false)
    expect(shareCodeSchema(true).parse('AA1 AA1 AA1')).toBe('AA1AA1AA1')
  })

  it('explains a wrong length', () => {
    const result = shareCodeSchema(false).safeParse('W12 3AB')
    expect(result.success).toBe(false)
    expect(result.error?.issues[0].message).toMatch(/9 characters/)
  })
})

describe('licence', () => {
  it('accepts a spaced, lower-case licence number', () => {
    expect(licenceNumberSchema.parse('nowak 803147 t99ab')).toBe('NOWAK803147T99AB')
  })

  it('rejects a malformed licence number', () => {
    expect(licenceNumberSchema.safeParse('N0WAK803147T99AB').success).toBe(false)
  })

  it('keeps the check code case and drops spaces', () => {
    expect(checkCodeSchema.parse('Hb Rh fp 7g')).toBe('HbRhfp7g')
    expect(checkCodeSchema.safeParse('short').success).toBe(false)
  })
})

describe('mobile number', () => {
  it('accepts UK mobiles in common formats', () => {
    expect(ukMobileSchema.parse('07700 900123')).toBe('07700900123')
    expect(ukMobileSchema.parse('+447700900123')).toBe('+447700900123')
  })

  it('rejects landlines', () => {
    expect(ukMobileSchema.safeParse('020 7946 0000').success).toBe(false)
  })
})
