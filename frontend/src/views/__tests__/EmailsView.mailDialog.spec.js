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
  importEmails: vi.fn(),
  getEmailPassword: vi.fn(),
  updateEmail: vi.fn()
}

vi.mock('@/store/emails', () => ({
  useEmailsStore: () => mockStore
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

describe('EmailsView mail content dialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStore.emails = []
    mockStore.loading = false
    mockStore.currentEmailId = null
    mockStore.currentMailRecords = []
    mockStore.hasSelectedEmails = false
    mockStore.selectedEmails = []
    mockStore.selectedEmailsCount = 0
    mockStore.fetchEmails.mockResolvedValue(undefined)
    mockStore.getEmailById.mockReturnValue(null)
    mockStore.getProcessingStatus.mockReturnValue(null)
  })

  it('closes content dialog and clears selectedMail', async () => {
    const wrapper = mount(EmailsView, {
      global: {
        directives: {
          loading: {}
        },
        stubs: {
          transition: false,
          teleport: true,
          'el-card': true,
          'el-button': true,
          'el-table': true,
          'el-table-column': true,
          'el-tag': true,
          'el-dialog': true,
          'el-tabs': true,
          'el-tab-pane': true,
          'el-form': true,
          'el-form-item': true,
          'el-select': true,
          'el-option': true,
          'el-input': true,
          'el-input-number': true,
          'el-switch': true,
          'el-icon': true,
          'el-tooltip': true,
          'el-progress': true
        }
      }
    })

    const vm = wrapper.vm
    vm.selectedMail = { id: 1, subject: 'demo', content: 'body' }
    vm.mailContentDialogVisible = true

    await vm.$nextTick()
    vm.handleCloseMailContentDialog()
    await vm.$nextTick()

    expect(vm.mailContentDialogVisible).toBe(false)
    expect(vm.selectedMail).toBe(null)
  })
})
