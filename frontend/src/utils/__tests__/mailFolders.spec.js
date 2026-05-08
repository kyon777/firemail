import { describe, expect, it } from 'vitest'
import {
  buildMailFolderFilters,
  filterMailRecordsByFolder,
  getMailFolderCategory
} from '@/utils/mailFolders'

describe('mail folder helpers', () => {
  const records = [
    { id: 1, folder: 'INBOX', subject: 'a' },
    { id: 2, folder: 'Inbox', subject: 'b' },
    { id: 3, folder: 'Junk', subject: 'c' },
    { id: 4, folder: 'junkemail', subject: 'd' },
    { id: 5, folder: 'Notes', subject: 'e' }
  ]

  it('classifies inbox, junk and other folders consistently', () => {
    expect(getMailFolderCategory('INBOX')).toEqual({ key: 'inbox', label: '收件箱' })
    expect(getMailFolderCategory('junkemail')).toEqual({ key: 'junk', label: '垃圾箱' })
    expect(getMailFolderCategory('Junk')).toEqual({ key: 'junk', label: '垃圾箱' })
    expect(getMailFolderCategory('Notes')).toEqual({ key: 'other', label: '其他' })
  })

  it('builds folder filters with aggregated counts', () => {
    expect(buildMailFolderFilters(records)).toEqual([
      { key: 'all', label: '全部', count: 5 },
      { key: 'inbox', label: '收件箱', count: 2 },
      { key: 'junk', label: '垃圾箱', count: 2 },
      { key: 'other', label: '其他', count: 1 }
    ])
  })

  it('filters records by logical folder category', () => {
    expect(filterMailRecordsByFolder(records, 'all')).toHaveLength(5)
    expect(filterMailRecordsByFolder(records, 'inbox').map(item => item.id)).toEqual([1, 2])
    expect(filterMailRecordsByFolder(records, 'junk').map(item => item.id)).toEqual([3, 4])
    expect(filterMailRecordsByFolder(records, 'other').map(item => item.id)).toEqual([5])
  })
})
