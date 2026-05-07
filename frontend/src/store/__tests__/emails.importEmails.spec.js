import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useEmailsStore } from '@/store/emails'
import api from '@/services/api'
import websocket from '@/services/websocket'

vi.mock('@/services/api', () => ({
  default: {
    emails: {
      import: vi.fn()
    }
  }
}))

const messageHandlers = {}

vi.mock('@/services/websocket', () => ({
  default: {
    isConnected: false,
    isAuthenticated: true,
    importEmails: vi.fn(),
    onConnect: vi.fn(),
    onDisconnect: vi.fn(),
    onMessage: vi.fn((type, handler) => {
      messageHandlers[type] = handler
    }),
    offMessage: vi.fn((type) => {
      delete messageHandlers[type]
    })
  }
}))

describe('emails store - importEmails', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    websocket.isConnected = false
    Object.keys(messageHandlers).forEach((key) => delete messageHandlers[key])
  })

  it('returns the api import result when websocket is disconnected', async () => {
    api.emails.import.mockResolvedValue({
      data: { total: 2, success: 1, failed: 1, failed_details: [{ reason: '邮箱已存在' }] }
    })
    const store = useEmailsStore()

    const result = await store.importEmails({ data: 'demo', mail_type: 'outlook' })

    expect(api.emails.import).toHaveBeenCalledWith({ data: 'demo', mail_type: 'outlook' })
    expect(result).toEqual({ total: 2, success: 1, failed: 1, failed_details: [{ reason: '邮箱已存在' }] })
  })

  it('waits for websocket import_result and resolves with the real import summary', async () => {
    websocket.isConnected = true
    websocket.importEmails.mockReturnValue(true)
    const store = useEmailsStore()

    const importPromise = store.importEmails({ data: 'demo', mail_type: 'outlook' })

    expect(websocket.importEmails).toHaveBeenCalledWith({ data: 'demo', mail_type: 'outlook' })
    expect(messageHandlers.import_result).toBeTypeOf('function')

    messageHandlers.import_result({
      total: 2,
      success: 0,
      failed: 2,
      failed_details: [{ reason: '邮箱已存在' }]
    })

    await expect(importPromise).resolves.toEqual({
      total: 2,
      success: 0,
      failed: 2,
      failed_details: [{ reason: '邮箱已存在' }]
    })
  })
})
