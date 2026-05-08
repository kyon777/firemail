import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import EmailDetailView from '@/views/EmailDetailView.vue'

const mockStore = {
  loading: false,
  currentMailRecords: [],
  fetchMailRecords: vi.fn(),
  checkEmail: vi.fn(),
  deleteEmail: vi.fn(),
  getEmailById: vi.fn(() => ({ id: 20, email: 'demo@outlook.com', last_check_time: null, created_at: null })),
  getProcessingStatus: vi.fn(() => null)
}

vi.mock('@/store/emails', () => ({
  useEmailsStore: () => mockStore
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { id: '20' }
  }),
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
  }
}))

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn()
  }
}))

vi.mock('@/components/EmailContentViewer.vue', () => ({
  default: {
    template: '<div class="viewer-stub">viewer</div>'
  }
}))

describe('EmailDetailView folder filter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStore.loading = false
    mockStore.currentMailRecords = [
      { id: 1, subject: 'Inbox A', content: 'body', folder: 'Inbox' },
      { id: 2, subject: 'Junk A', content: 'body', folder: 'Junk' },
      { id: 3, subject: 'Other A', content: 'body', folder: 'Notes' }
    ]
  })

  it('filters detail page mail records by logical folder category', async () => {
    const wrapper = mount(EmailDetailView, {
      global: {
        stubs: {
          transition: false,
          teleport: true,
          'el-page-header': true,
          'el-button': true,
          'el-icon': true,
          'el-descriptions': true,
          'el-descriptions-item': true,
          'el-card': true,
          'el-input': true,
          'el-empty': true,
          'el-collapse': true,
          'el-collapse-item': true,
          'el-tag': true,
          'el-dialog': true,
          'el-upload': true,
          'el-form': true,
          'el-form-item': true
        },
        directives: {
          loading: {}
        }
      }
    })

    const vm = wrapper.vm

    expect(vm.mailFolderFilters).toEqual([
      { key: 'all', label: '全部', count: 3 },
      { key: 'inbox', label: '收件箱', count: 1 },
      { key: 'junk', label: '垃圾箱', count: 1 },
      { key: 'other', label: '其他', count: 1 }
    ])

    vm.selectedMailFolderFilter = 'junk'
    await vm.$nextTick()
    expect(vm.filteredMailRecords.map(mail => mail.id)).toEqual([2])
  })
})
