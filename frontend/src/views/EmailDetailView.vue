<template>
  <div class="email-detail-container">
    <div class="header-section">
      <el-page-header @back="goBack" :title="'返回邮箱列表'">
        <template #content>
          <span class="email-title">{{ email ? email.email : '加载中...' }}</span>
        </template>
      </el-page-header>

      <div class="actions" v-if="email">
        <el-button type="primary" @click="checkEmail" :disabled="isProcessing" :loading="loading">
          <el-icon><Download /></el-icon> 收取邮件
        </el-button>
        <el-button type="success" @click="showUploadDialog" :disabled="isProcessing">
          <el-icon><Upload /></el-icon> 上传邮件文件
        </el-button>
        <el-button type="danger" @click="confirmDelete" :disabled="isProcessing">
          <el-icon><Delete /></el-icon> 删除邮箱
        </el-button>
      </div>
    </div>

    <div class="email-info" v-if="email">
      <el-descriptions title="邮箱信息" :column="1" border>
        <el-descriptions-item label="邮箱地址">{{ email.email }}</el-descriptions-item>
        <el-descriptions-item label="最后检查时间">{{ formatDate(email.last_check_time) }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatDate(email.created_at) }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <div class="mail-records" v-loading="loading">
      <el-card class="mail-card">
        <template #header>
          <div class="mail-header">
            <span>邮件列表</span>
            <el-input
              v-model="searchQuery"
              placeholder="搜索邮件主题或内容"
              clearable
              class="search-input"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </div>
        </template>

        <div v-if="filteredMailRecords.length === 0" class="no-mails">
          <el-empty description="暂无邮件记录" />
        </div>

        <div v-else class="mail-detail-layout">
          <aside class="mail-folder-sidebar">
            <button
              v-for="folderFilter in mailFolderFilters"
              :key="folderFilter.key"
              type="button"
              class="mail-folder-item"
              :class="{ active: selectedMailFolderFilter === folderFilter.key }"
              @click="selectedMailFolderFilter = folderFilter.key"
            >
              <span>{{ folderFilter.label }}</span>
              <el-tag size="small" effect="plain">{{ folderFilter.count }}</el-tag>
            </button>
          </aside>

          <div class="mail-detail-list">
            <el-collapse accordion @change="handleCollapseChange">
              <el-collapse-item v-for="mail in filteredMailRecords" :key="mail.id" :name="mail.id">
                <template #title>
                  <div class="mail-title">
                    <span class="subject">{{ mail.subject || '(无主题)' }}</span>
                    <div class="mail-title-meta">
                      <el-tag size="small" :type="getFolderTagType(mail.folder)">
                        {{ getFolderLabel(mail.folder) }}
                      </el-tag>
                      <span class="date">{{ formatDate(mail.received_time) }}</span>
                      <el-tag v-if="mail.has_attachments" size="small" type="success" class="attachment-tag">
                        <el-icon><Document /></el-icon> 附件
                      </el-tag>
                    </div>
                  </div>
                </template>

                <div class="mail-content">
                  <EmailContentViewer
                    :mail="mail"
                    :attachments="mailAttachments[mail.id] || []"
                    :loading-attachments="loadingAttachments"
                  />
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
      </el-card>
    </div>
  </div>

  <el-dialog
    v-model="uploadDialogVisible"
    title="上传邮件文件"
    width="500px"
  >
    <el-form>
      <el-form-item label="选择邮件文件">
        <el-upload
          ref="uploadRef"
          class="upload-demo"
          drag
          action="#"
          :auto-upload="false"
          :limit="1"
          :on-change="handleFileChange"
          :on-exceed="handleExceed"
          :file-list="fileList"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">
            拖拽文件到此处或 <em>点击上传</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              支持 .eml 格式的邮件文件
            </div>
          </template>
        </el-upload>
      </el-form-item>
    </el-form>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="uploadDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="uploadEmailFile" :loading="uploading">
          上传
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Download, Delete, Search, Upload, UploadFilled, Document } from '@element-plus/icons-vue'
import { useEmailsStore } from '@/store/emails'
import dayjs from 'dayjs'
import axios from 'axios'
import EmailContentViewer from '@/components/EmailContentViewer.vue'
import { buildMailFolderFilters, filterMailRecordsByFolder, getMailFolderCategory } from '@/utils/mailFolders'

const route = useRoute()
const router = useRouter()
const emailsStore = useEmailsStore()
const searchQuery = ref('')
const selectedMailFolderFilter = ref('all')
const mailAttachments = ref({})
const loadingAttachments = ref(false)

const uploadDialogVisible = ref(false)
const uploadRef = ref(null)
const fileList = ref([])
const uploading = ref(false)

const emailId = computed(() => parseInt(route.params.id))
const email = computed(() => emailsStore.getEmailById(emailId.value))
const loading = computed(() => emailsStore.loading)
const mailRecords = computed(() => emailsStore.currentMailRecords)
const mailFolderFilters = computed(() => buildMailFolderFilters(mailRecords.value))

const filteredMailRecords = computed(() => {
  const records = filterMailRecordsByFolder(mailRecords.value, selectedMailFolderFilter.value)
  const query = searchQuery.value.trim().toLowerCase()

  if (!query) return records

  return records.filter(mail => {
    const subject = String(mail?.subject || '').toLowerCase()
    const content = typeof mail?.content === 'object'
      ? String(mail?.content?.content || '').toLowerCase()
      : String(mail?.content || '').toLowerCase()

    return subject.includes(query) || content.includes(query)
  })
})

const isProcessing = computed(() => {
  const status = getProcessingStatus(emailId.value)
  return status && status.progress > 0 && status.progress < 100
})

const getProcessingStatus = (id) => {
  return emailsStore.getProcessingStatus(id)
}

const formatDate = (dateString) => {
  if (!dateString) return '无'
  return dayjs(dateString).format('YYYY-MM-DD HH:mm:ss')
}

const goBack = () => {
  router.push('/emails')
}

const loadMailAttachments = async (mailId) => {
  if (mailAttachments.value[mailId]) {
    return
  }

  loadingAttachments.value = true
  try {
    const response = await axios.get(`/api/mail_records/${mailId}/attachments`, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem('token')}`
      }
    })

    if (response.status === 200) {
      mailAttachments.value[mailId] = response.data
    } else {
      ElMessage.error('获取附件列表失败')
    }
  } catch (error) {
    console.error('获取附件列表失败:', error)
    ElMessage.error('获取附件列表失败')
  } finally {
    loadingAttachments.value = false
  }
}

const checkEmail = () => {
  emailsStore.checkEmail(emailId.value)
  ElMessage.success('开始收取邮件')
}

const confirmDelete = () => {
  if (!email.value) return

  ElMessageBox.confirm(
    `确定要删除邮箱 ${email.value.email} 吗？所有相关的邮件记录也将被删除。`,
    '删除确认',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(() => {
    emailsStore.deleteEmail(emailId.value)
    ElMessage.success('删除成功')
    router.push('/emails')
  }).catch(() => {})
}

watch(emailId, (newId) => {
  if (newId) {
    selectedMailFolderFilter.value = 'all'
    emailsStore.fetchMailRecords(newId)
  }
})

const handleCollapseChange = (activeNames) => {
  if (activeNames && typeof activeNames === 'number') {
    const mail = mailRecords.value.find(item => item.id === activeNames)
    if (mail && mail.has_attachments) {
      loadMailAttachments(mail.id)
    }
  }
}

const showUploadDialog = () => {
  uploadDialogVisible.value = true
  fileList.value = []
}

const handleFileChange = (file) => {
  fileList.value = [file]
}

const handleExceed = () => {
  ElMessage.warning('只能上传一个文件')
}

const uploadEmailFile = async () => {
  if (fileList.value.length === 0) {
    ElMessage.warning('请选择要上传的文件')
    return
  }

  const file = fileList.value[0].raw
  const fileName = file.name
  const fileExt = fileName.substring(fileName.lastIndexOf('.')).toLowerCase()
  const allowedExtensions = ['.eml', '.txt', '.msg', '.mbox', '.emlx']
  if (!allowedExtensions.includes(fileExt)) {
    ElMessage.error(`只支持${allowedExtensions.join('、')}格式的邮件文件`)
    return
  }

  const formData = new FormData()
  formData.append('file', file)

  uploading.value = true
  try {
    const response = await axios.post(
      `/api/emails/${emailId.value}/upload_email_file`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        }
      }
    )

    if (response.data.success) {
      ElMessage.success('邮件文件上传成功')
      uploadDialogVisible.value = false
      emailsStore.fetchMailRecords(emailId.value)
    } else {
      ElMessage.error(response.data.error || '上传失败')
    }
  } catch (error) {
    console.error('上传邮件文件失败:', error)
    ElMessage.error(error.response?.data?.error || '上传失败')
  } finally {
    uploading.value = false
  }
}

const getFolderLabel = (folder) => getMailFolderCategory(folder).label

const getFolderTagType = (folder) => {
  const folderKey = getMailFolderCategory(folder).key
  if (folderKey === 'inbox') return 'primary'
  if (folderKey === 'junk') return 'danger'
  return 'info'
}

onMounted(() => {
  if (emailId.value) {
    selectedMailFolderFilter.value = 'all'
    emailsStore.fetchMailRecords(emailId.value)
  }
})
</script>

<style scoped>
.email-detail-container {
  max-width: 1280px;
  margin: 0 auto;
  padding: 20px;
}

.header-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.email-title {
  font-size: 18px;
  font-weight: bold;
  color: #409eff;
}

.email-info {
  margin-bottom: 20px;
}

.mail-card {
  margin-bottom: 20px;
}

.mail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.search-input {
  max-width: 300px;
}

.no-mails {
  padding: 40px 0;
}

.mail-detail-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.mail-folder-sidebar {
  width: 148px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mail-folder-item {
  width: 100%;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  background: #fff;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  transition: all 0.2s ease;
  color: #303133;
}

.mail-folder-item:hover,
.mail-folder-item.active {
  border-color: #409eff;
  background: #ecf5ff;
  color: #409eff;
}

.mail-detail-list {
  flex: 1;
  min-width: 0;
}

.mail-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding-right: 20px;
  gap: 16px;
}

.subject {
  font-weight: bold;
  margin-right: 10px;
}

.mail-title-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.date {
  color: #909399;
  font-size: 0.9em;
}

.mail-content {
  padding: 10px;
  background-color: #f8f9fa;
  border-radius: 4px;
}

.attachment-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

@media (max-width: 768px) {
  .header-section {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .actions {
    width: 100%;
    display: flex;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
  }

  .mail-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .search-input {
    max-width: 100%;
    width: 100%;
  }

  .mail-detail-layout {
    flex-direction: column;
  }

  .mail-folder-sidebar {
    width: 100%;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .mail-title {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .mail-title-meta {
    flex-wrap: wrap;
  }
}
</style>
