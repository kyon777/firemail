import { describe, expect, it } from 'vitest'
import { getImportResultFeedback } from '@/utils/importResult'

describe('import result feedback', () => {
  it('returns success feedback when all imports succeed', () => {
    expect(getImportResultFeedback({ total: 3, success: 3, failed: 0 })).toEqual({
      type: 'success',
      message: '批量导入完成：成功 3 个，失败 0 个'
    })
  })

  it('returns warning feedback when import partially succeeds', () => {
    expect(getImportResultFeedback({ total: 3, success: 2, failed: 1 })).toEqual({
      type: 'warning',
      message: '批量导入完成：成功 2 个，失败 1 个'
    })
  })

  it('returns warning feedback when all imports fail, including duplicates', () => {
    expect(
      getImportResultFeedback({
        total: 2,
        success: 0,
        failed: 2,
        failed_details: [{ reason: '邮箱已存在' }, { reason: '邮箱已存在' }]
      })
    ).toEqual({
      type: 'warning',
      message: '批量导入完成：成功 0 个，失败 2 个'
    })
  })
})
