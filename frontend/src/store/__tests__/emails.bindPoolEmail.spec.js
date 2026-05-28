import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useEmailsStore } from '@/store/emails'
import api from '@/services/api'
import websocket from '@/services/websocket'

vi.mock('@/services/api', () => ({
  default: {
    mailPool: {
      bind: vi.fn()
    },
    emails: {
      getAll: vi.fn()
    }
  }
}))

vi.mock('@/services/websocket', () => ({
  default: {
    isConnected: false,
    onConnect: vi.fn(),
    onDisconnect: vi.fn(),
    onMessage: vi.fn(),
    offMessage: vi.fn(),
    send: vi.fn()
  }
}))

describe('emails store - bindPoolEmail', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    websocket.isConnected = false
  })

  it('binds a pool email through the private mail pool API and refreshes emails', async () => {
    api.mailPool.bind.mockResolvedValue({ data: { email_id: 7, email: 'pool1@outlook.com' } })
    api.emails.getAll.mockResolvedValue([{ id: 7, email: 'pool1@outlook.com' }])
    const store = useEmailsStore()

    const result = await store.bindPoolEmail('pool1@outlook.com')

    expect(api.mailPool.bind).toHaveBeenCalledWith('pool1@outlook.com')
    expect(api.emails.getAll).toHaveBeenCalled()
    expect(store.emails).toEqual([{ id: 7, email: 'pool1@outlook.com' }])
    expect(result).toEqual({ email_id: 7, email: 'pool1@outlook.com' })
  })
})
