import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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
    websocket.isConnected = false
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('uses websocket first and marks email as processing immediately', async () => {
    websocket.isConnected = true
    websocket.send.mockReturnValue(true)
    const store = useEmailsStore()

    await store.checkEmail(42)

    expect(websocket.send).toHaveBeenCalledWith('check_emails', { email_ids: [42] })
    expect(store.processingEmails[42]).toEqual(expect.objectContaining({ progress: 0, message: '开始检查...' }))
    expect(api.emails.check).not.toHaveBeenCalled()
  })

  it('falls back to http when websocket is disconnected', async () => {
    websocket.isConnected = false
    api.emails.check.mockResolvedValue({ data: { success: true, message: 'started' }, status: 202 })
    const store = useEmailsStore()

    await store.checkEmail(7)

    expect(api.emails.check).toHaveBeenCalledWith([7])
    expect(store.processingEmails[7]).toEqual(expect.objectContaining({ progress: 0, message: '开始检查...' }))
  })

  it('falls back to http when websocket send returns false', async () => {
    websocket.isConnected = true
    websocket.send.mockReturnValue(false)
    api.emails.check.mockResolvedValue({ data: { success: true, message: 'started' }, status: 202 })
    const store = useEmailsStore()

    await store.checkEmail(8)

    expect(websocket.send).toHaveBeenCalledWith('check_emails', { email_ids: [8] })
    expect(api.emails.check).toHaveBeenCalledWith([8])
    expect(store.processingEmails[8]).toEqual(expect.objectContaining({ progress: 0, message: '开始检查...' }))
  })

  it('returns processing status on http 409 conflict', async () => {
    websocket.isConnected = false
    api.emails.check.mockRejectedValue({
      response: {
        status: 409,
        data: { message: '邮箱正在处理中' }
      }
    })
    const store = useEmailsStore()

    const result = await store.checkEmail(9)

    expect(result).toEqual({ success: false, message: '邮箱正在处理中', status: 'processing' })
    expect(store.processingEmails[9]).toEqual(expect.objectContaining({ progress: 0, message: '邮箱正在处理中' }))
  })

  it('cleans processing status after check_progress reaches 100', async () => {
    vi.useFakeTimers()
    websocket.isConnected = true
    websocket.send.mockReturnValue(true)
    const store = useEmailsStore()
    store.fetchEmails = vi.fn()
    store.fetchMailRecords = vi.fn()
    store.initWebSocketListeners()

    await store.checkEmail(10)

    const checkProgressHandler = websocket.onMessage.mock.calls.find(([type]) => type === 'check_progress')[1]
    checkProgressHandler({ email_id: 10, progress: 100, message: '完成' })

    vi.advanceTimersByTime(1000)

    expect(store.fetchEmails).toHaveBeenCalledTimes(1)
    expect(store.processingEmails[10]).toBeUndefined()
  })

  it('does not let an old completion timer delete a newer processing state', async () => {
    vi.useFakeTimers()
    websocket.isConnected = true
    websocket.send.mockReturnValue(true)
    const store = useEmailsStore()
    store.fetchEmails = vi.fn()
    store.fetchMailRecords = vi.fn()
    store.initWebSocketListeners()

    await store.checkEmail(11)

    const checkProgressHandler = websocket.onMessage.mock.calls.find(([type]) => type === 'check_progress')[1]
    checkProgressHandler({ email_id: 11, progress: 100, message: '第一轮完成' })

    await store.checkEmail(11)
    vi.advanceTimersByTime(1000)

    expect(store.processingEmails[11]).toEqual(expect.objectContaining({ progress: 0, message: '开始检查...' }))
  })
})
