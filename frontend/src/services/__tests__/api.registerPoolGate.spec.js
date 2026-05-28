import { beforeEach, describe, expect, it, vi } from 'vitest'

const axiosMock = vi.hoisted(() => {
  const instance = {
    defaults: { headers: { common: {} }, baseURL: '' },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() }
    },
    get: vi.fn(),
    post: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn()
  }

  return {
    instance,
    create: vi.fn(() => instance)
  }
})

vi.mock('axios', () => ({
  default: {
    create: axiosMock.create
  }
}))

describe('api register pool gate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    axiosMock.instance.post.mockResolvedValue({ data: {} })
    window.API_URL = undefined
  })

  it('sends verification_email to backend register endpoint', async () => {
    const api = (await import('@/services/api')).default

    await api.register('customer', 'zz123456', 'customer@outlook.com')

    expect(axiosMock.instance.post).toHaveBeenCalledWith('/auth/register', {
      username: 'customer',
      password: 'zz123456',
      verification_email: 'customer@outlook.com'
    })
  })
})
