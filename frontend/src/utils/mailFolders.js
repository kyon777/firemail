const INBOX_ALIASES = new Set(['inbox'])
const JUNK_ALIASES = new Set(['junk', 'junkemail', 'junk e-mail', 'spam'])

function normalizeFolderName(folder) {
  return String(folder || '').trim().toLowerCase()
}

export function getMailFolderCategory(folder) {
  const normalized = normalizeFolderName(folder)

  if (INBOX_ALIASES.has(normalized)) {
    return { key: 'inbox', label: '收件箱' }
  }

  if (JUNK_ALIASES.has(normalized)) {
    return { key: 'junk', label: '垃圾箱' }
  }

  return { key: 'other', label: '其他' }
}

export function buildMailFolderFilters(mailRecords = []) {
  const counts = {
    all: Array.isArray(mailRecords) ? mailRecords.length : 0,
    inbox: 0,
    junk: 0,
    other: 0
  }

  for (const mail of mailRecords || []) {
    const { key } = getMailFolderCategory(mail?.folder)
    counts[key] += 1
  }

  return [
    { key: 'all', label: '全部', count: counts.all },
    { key: 'inbox', label: '收件箱', count: counts.inbox },
    { key: 'junk', label: '垃圾箱', count: counts.junk },
    { key: 'other', label: '其他', count: counts.other }
  ].filter(item => item.key === 'all' || item.count > 0)
}

export function filterMailRecordsByFolder(mailRecords = [], folderKey = 'all') {
  if (!Array.isArray(mailRecords) || folderKey === 'all') {
    return Array.isArray(mailRecords) ? mailRecords : []
  }

  return mailRecords.filter(mail => getMailFolderCategory(mail?.folder).key === folderKey)
}
