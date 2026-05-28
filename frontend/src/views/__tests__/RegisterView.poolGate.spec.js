import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import RegisterView from '@/views/auth/RegisterView.vue'

vi.mock('@/services/api', () => ({
  default: {
    getConfig: vi.fn().mockResolvedValue({ data: { allow_register: true } })
  }
}))

const mountView = () => {
  const registerAndLogin = vi.fn().mockResolvedValue({ success: true })
  const push = vi.fn()

  const wrapper = mount(RegisterView, {
    global: {
      mocks: {
        $store: { dispatch: vi.fn() },
        $router: { push }
      },
      stubs: {
        'router-link': { template: '<a><slot /></a>' }
      }
    }
  })
  wrapper.vm.registerAndLogin = registerAndLogin

  return { wrapper, registerAndLogin, push }
}

describe('RegisterView pool registration gate', () => {
  it('requires a verification email from the internal mail pool before submit is valid', async () => {
    const { wrapper } = mountView()

    await wrapper.setData({
      username: 'customer',
      password: 'zz123456',
      confirmPassword: 'zz123456'
    })

    expect(wrapper.vm.formValid).toBe(false)

    await wrapper.setData({ verificationEmail: 'customer@outlook.com' })

    expect(wrapper.vm.formValid).toBe(true)
  })

  it('submits verification email to registerAndLogin without exposing any pool credentials', async () => {
    const { wrapper, registerAndLogin, push } = mountView()

    await wrapper.setData({
      username: 'customer',
      password: 'zz123456',
      confirmPassword: 'zz123456',
      verificationEmail: ' Customer@Outlook.com '
    })

    await wrapper.vm.handleRegister()

    expect(registerAndLogin).toHaveBeenCalledWith({
      username: 'customer',
      password: 'zz123456',
      verificationEmail: 'Customer@Outlook.com'
    })
    expect(push).toHaveBeenCalledWith('/')
  })
})
