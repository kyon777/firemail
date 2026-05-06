import { describe, expect, it } from 'vitest'
import { normalizeOutlookImportLine, validateOutlookImportData } from '@/utils/importFormats'

describe('importFormats', () => {
  it('normalizes legacy outlook import lines with refresh token before client id', () => {
    const result = normalizeOutlookImportLine(
      'demo@outlook.com----x----M.C549_SN1.token-value$$----9e5f94bc-e8a4-4e73-b8be-63364c29d753'
    )

    expect(result).toEqual({
      email: 'demo@outlook.com',
      password: 'x',
      client_id: '9e5f94bc-e8a4-4e73-b8be-63364c29d753',
      refresh_token: 'M.C549_SN1.token-value$$',
      format: 'legacy'
    })
  })

  it('accepts both standard and legacy outlook batch import data', () => {
    const validation = validateOutlookImportData(`
demo1@outlook.com----x----9e5f94bc-e8a4-4e73-b8be-63364c29d753----M.C549_SN1.token-value$$
demo2@outlook.com----x----M.C549_SN1.token-value-2$$----9e5f94bc-e8a4-4e73-b8be-63364c29d753
    `)

    expect(validation).toEqual({ valid: true })
  })
})
