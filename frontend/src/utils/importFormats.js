const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const looksLikeClientId = (value) => UUID_REGEX.test((value || '').trim())

const looksLikeRefreshToken = (value) => {
  const normalized = (value || '').trim()
  return normalized.startsWith('M.') || normalized.length >= 40 || /[!*$]/.test(normalized)
}

export function normalizeOutlookImportLine(line) {
  const parts = line.split('----').map(part => part.trim())

  if (parts.length !== 4) {
    throw new Error('格式错误，需要使用4段数据：邮箱----密码/占位----ClientID/RefreshToken----RefreshToken/ClientID')
  }

  const [email, password, third, fourth] = parts
  if (!email || !password || !third || !fourth) {
    throw new Error('存在空白字段')
  }

  if (!EMAIL_REGEX.test(email)) {
    throw new Error('邮箱格式不正确')
  }

  const isLegacyOrder =
    looksLikeRefreshToken(third) &&
    looksLikeClientId(fourth) &&
    !looksLikeClientId(third)

  return {
    email,
    password,
    client_id: isLegacyOrder ? fourth : third,
    refresh_token: isLegacyOrder ? third : fourth,
    format: isLegacyOrder ? 'legacy' : 'standard'
  }
}

export function validateOutlookImportData(value) {
  if (!value || !value.trim()) {
    return { valid: true }
  }

  const lines = value.trim().split('\n')
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index].trim()
    if (!line) continue

    try {
      normalizeOutlookImportLine(line)
    } catch (error) {
      return {
        valid: false,
        line: index + 1,
        message: `第 ${index + 1} 行${error.message}`
      }
    }
  }

  return { valid: true }
}
