import { beforeEach, describe, expect, it, vi } from 'vitest'
import authModule from '@/store/modules/auth'
import api from '@/services/api'

vi.mock('@/services/api', () => ({
  default: {
    register: vi.fn(),
    login: vi.fn()
  }
}))

vi.mock('@/router', () => ({
  default: {
    currentRoute: { value: { meta: {} } },
    push: vi.fn()
  }
}))

describe('auth store registration pool gate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.register.mockResolvedValue({ data: { message: '注册成功' } })
    api.login.mockResolvedValue({
      data: {
        token: 'token',
        user: { id: 1, username: 'customer', is_admin: false }
      }
    })
  })

  it('passes verification email to register api', async () => {
    const commit = vi.fn()

    await authModule.actions.register(
      { commit },
      {
        username: 'customer',
        password: 'zz123456',
        verificationEmail: 'customer@outlook.com'
      }
    )

    expect(api.register).toHaveBeenCalledWith(
      'customer',
      'zz123456',
      'customer@outlook.com'
    )
  })

  it('keeps verification email through registerAndLogin flow', async () => {
    const dispatch = vi.fn()
      .mockResolvedValueOnce({ message: '注册成功' })
      .mockResolvedValueOnce({ id: 1, username: 'customer', isAdmin: false })

    const result = await authModule.actions.registerAndLogin(
      { dispatch, commit: vi.fn() },
      {
        username: 'customer',
        password: 'zz123456',
        verificationEmail: 'customer@outlook.com'
      }
    )

    expect(dispatch).toHaveBeenNthCalledWith(1, 'register', {
      username: 'customer',
      password: 'zz123456',
      verificationEmail: 'customer@outlook.com'
    })
    expect(dispatch).toHaveBeenNthCalledWith(2, 'login', {
      username: 'customer',
      password: 'zz123456'
    })
    expect(result.success).toBe(true)
  })
})
