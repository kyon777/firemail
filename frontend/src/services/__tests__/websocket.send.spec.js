import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('websocket service - send', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('replays a queued unauthenticated request only once after auth succeeds', async () => {
    localStorage.setItem('token', 'test-token')
    const { default: websocket } = await import('@/services/websocket')

    websocket.isConnected = true
    websocket.isAuthenticated = false
    websocket.socket = {
      send: vi.fn()
    }

    const doSendSpy = vi.spyOn(websocket, 'doSend')

    const result = websocket.send('check_emails', { email_ids: [42] })
    expect(result).toBe(false)

    websocket.handleMessage({ type: 'auth_result', success: true })
    vi.advanceTimersByTime(2500)

    const replayCalls = doSendSpy.mock.calls.filter(([type]) => type === 'check_emails')
    expect(replayCalls).toHaveLength(1)
    expect(replayCalls[0]).toEqual(['check_emails', { email_ids: [42] }])
  })
})
