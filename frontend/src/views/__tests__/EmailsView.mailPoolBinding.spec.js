import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import EmailsView from '@/views/EmailsView.vue'

const mockStore = {
  emails: [],
  loading: false,
  currentEmailId: null,
  currentMailRecords: [],
  hasSelectedEmails: false,
  selectedEmails: [],
  selectedEmailsCount: 0,
  fetchEmails: vi.fn().mockResolvedValue(undefined),
  initWebSocketListeners: vi.fn(),
  getEmailById: vi.fn(() => null),
  getProcessingStatus: vi.fn(() => null),
  deleteEmail: vi.fn(),
  deleteEmails: vi.fn(),
  checkEmail: vi.fn(),
  checkEmails: vi.fn(),
  fetchMailRecords: vi.fn(),
  addEmail: vi.fn(),
  bindPoolEmail: vi.fn().mockResolvedValue({ email_id: 7 }),
  batchBindPoolEmails: vi.fn().mockResolvedValue({
    total: 2,
    summary: { bound: 1, not_found: 1 },
    results: [
      { line: 1, email: 'a@outlook.com', status: 'bound', message: '\u90ae\u7bb1\u7ed1\u5b9a\u6210\u529f' },
      { line: 2, email: 'missing@outlook.com', status: 'not_found', message: '\u8be5\u90ae\u7bb1\u4e0d\u5728\u53ef\u7ed1\u5b9a\u90ae\u7bb1\u5e93\u4e2d' }
    ]
  }),
  importEmails: vi.fn(),
  getEmailPassword: vi.fn(),
  updateEmail: vi.fn()
}

let mockIsAdmin = false

vi.mock('@/store/emails', () => ({
  useEmailsStore: () => mockStore
}))

vi.mock('vuex', () => ({
  useStore: () => ({
    getters: {
      'auth/isAdmin': mockIsAdmin
    }
  })
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn()
  })
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn()
  },
  ElMessageBox: {
    confirm: vi.fn()
  },
  ElLoading: {
    service: vi.fn(() => ({
      close: vi.fn()
    }))
  }
}))

vi.mock('@/components/EmailContentViewer.vue', () => ({
  default: {
    template: '<div class="viewer-stub">viewer</div>'
  }
}))

const mountView = () => mount(EmailsView, {
  global: {
    directives: {
      loading: {}
    },
    stubs: {
      transition: false,
      teleport: true,
      'el-card': { template: '<div><slot name="header" /><slot /></div>' },
      'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
      'el-table': true,
      'el-table-column': true,
      'el-tag': true,
      'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
      'el-tabs': { template: '<div><slot /></div>' },
      'el-tab-pane': { template: '<div><slot /></div>' },
      'el-form': { template: '<form><slot /></form>', methods: { validate: () => Promise.resolve() } },
      'el-form-item': { template: '<div><slot /></div>' },
      'el-select': true,
      'el-option': true,
      'el-input': { template: '<textarea />' },
      'el-input-number': true,
      'el-switch': true,
      'el-icon': true,
      'el-tooltip': true,
      'el-progress': true
    }
  }
})

describe('EmailsView mail pool binding', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockIsAdmin = false
  })

  it('shows bind email entry instead of admin import controls for normal users', () => {
    const wrapper = mountView()

    expect(wrapper.text()).toContain('\u7ed1\u5b9a\u90ae\u7bb1')
    expect(wrapper.text()).not.toContain('\u6279\u91cf\u5bfc\u5165')
  })

  it('shows batch bind entry for normal users', () => {
    const wrapper = mountView()

    expect(wrapper.text()).toContain('\u6279\u91cf\u7ed1\u5b9a')
    expect(wrapper.text()).toContain('\u4e00\u884c\u4e00\u4e2a\u90ae\u7bb1')
  })

  it('submits multiline pool emails and keeps result summary visible', async () => {
    const wrapper = mountView()

    wrapper.vm.batchBindForm.emails = 'a@outlook.com\nmissing@outlook.com'
    await wrapper.vm.handleBatchBindPoolEmails()

    expect(mockStore.batchBindPoolEmails).toHaveBeenCalledWith('a@outlook.com\nmissing@outlook.com')
    expect(wrapper.vm.batchBindResult.summary.bound).toBe(1)
    expect(wrapper.vm.batchBindResult.summary.not_found).toBe(1)
  })
})
