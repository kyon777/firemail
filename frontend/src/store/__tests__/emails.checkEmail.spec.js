import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useEmailsStore } from '@/store/emails'
import api from '@/services/api'
import websocket from '@/services/websocket'

vi.mock('@/services/api', () => ({
  default: {
    emails: {
      check: vi.fn()
    }
  }
}))

vi.mock('@/services/websocket', () => ({
  default: {
    isConnected: false,
    send: vi.fn(),
    onConnect: vi.fn(),
    onDisconnect: vi.fn(),
    onMessage: vi.fn()
  }
}))

describe('emails store - checkEmail', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('uses websocket first and marks email as processing immediately', async () => {
    websocket.isConnected = true
    const store = useEmailsStore()

    await store.checkEmail(42)

    expect(websocket.send).toHaveBeenCalledWith('check_emails', { email_ids: [42] })
    expect(store.processingEmails[42]).toEqual({ progress: 0, message: '开始检查...' })
    expect(api.emails.check).not.toHaveBeenCalled()
  })

  it('falls back to http when websocket is disconnected', async () => {
    websocket.isConnected = false
    api.emails.check.mockResolvedValue({ data: { success: true, message: 'started' }, status: 202 })
    const store = useEmailsStore()

    await store.checkEmail(7)

    expect(api.emails.check).toHaveBeenCalledWith([7])
    expect(store.processingEmails[7]).toEqual({ progress: 0, message: '开始检查...' })
  })
})
