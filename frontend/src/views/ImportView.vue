<template>
  <div class="import-container">
    <h1 class="page-title">批量导入邮箱</h1>
    
    <el-card class="import-card">
      <div class="import-form">
        <el-alert
          type="info"
          title="导入格式说明"
          :closable="false"
          show-icon
        >
          <p>请选择邮箱类型，然后按照相应格式输入邮箱信息，每行一个：</p>
          <p v-if="formData.mailType === 'outlook'"><code>邮箱地址----密码/占位----客户端ID----RefreshToken</code></p>
          <p v-if="formData.mailType === 'outlook'"><code>兼容旧版右键导出：邮箱地址----密码/占位----RefreshToken----客户端ID</code></p>
          <p>示例：example@outlook.com----x----9e5f94bc-e8a4-4e73-b8be-63364c29d753----M.C511_BL2...</p>
          <p>旧版示例：example@outlook.com----x----M.C511_BL2...----9e5f94bc-e8a4-4e73-b8be-63364c29d753</p>
        </el-alert>
        
        <el-form :model="formData" ref="formRef" :rules="rules" label-position="top">
          <el-form-item label="选择邮箱类型" prop="mailType">
            <el-select v-model="formData.mailType" placeholder="请选择邮箱类型">
              <el-option
                label="Outlook/Hotmail"
                value="outlook"
              />
              <!-- 为以后扩展预留 -->
            </el-select>
          </el-form-item>
          
          <el-form-item label="批量邮箱数据" prop="importData">
            <el-input
              v-model="formData.importData"
              type="textarea"
              :rows="10"
              placeholder="请输入需要批量导入的邮箱数据，每行一个"
            />
          </el-form-item>
          
          <el-form-item>
            <el-button type="primary" @click="submitForm" :loading="loading">
              <el-icon><Upload /></el-icon> 开始导入
            </el-button>
            <el-button @click="resetForm">
              <el-icon><RefreshRight /></el-icon> 重置
            </el-button>
          </el-form-item>
        </el-form>
      </div>
      
      <div class="import-result" v-if="importResult">
        <el-divider>导入结果</el-divider>
        
        <el-result
          :icon="importResult.success > 0 ? 'success' : 'warning'"
          :title="getResultTitle()"
          :sub-title="getResultSubtitle()"
        >
          <template #extra>
            <el-button type="primary" @click="navigateToEmails">查看邮箱列表</el-button>
            <el-button @click="resetForm">继续导入</el-button>
          </template>
        </el-result>
        
        <template v-if="importResult.failed > 0">
          <h3>失败详情</h3>
          <el-table :data="importResult.failed_details" stripe style="width: 100%">
            <el-table-column prop="line" label="行号" width="80" />
            <el-table-column prop="content" label="内容" min-width="200" show-overflow-tooltip />
            <el-table-column prop="reason" label="失败原因" width="150" />
          </el-table>
        </template>
      </div>
    </el-card>
    
    <el-card class="guide-card">
      <template #header>
        <div class="card-header">
          <span>如何获取 RefreshToken</span>
        </div>
      </template>
      
      <div class="guide-content" v-if="formData.mailType === 'outlook'">
        <p>获取 RefreshToken 的步骤：</p>
        <ol>
          <li>登录您的 Microsoft 账户</li>
          <li>访问 Microsoft Azure 门户</li>
          <li>注册应用并获取客户端 ID</li>
          <li>设置 API 权限和回调 URL</li>
          <li>使用 OAuth 流程获取初始 RefreshToken</li>
        </ol>
        <p>详细说明可参考：<a href="https://learn.microsoft.com/zh-cn/azure/active-directory/develop/v2-oauth2-auth-code-flow" target="_blank">Microsoft OAuth 2.0 授权代码流</a></p>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Upload, RefreshRight } from '@element-plus/icons-vue'
import { useEmailsStore } from '@/store/emails'
import WebSocketService from '@/services/websocket'
import { validateOutlookImportData } from '@/utils/importFormats'

const router = useRouter()
const emailsStore = useEmailsStore()
const formRef = ref(null)
const loading = ref(false)
const importResult = ref(null)

// 表单数据
const formData = reactive({
  mailType: '', // 默认为空，让用户选择
  importData: ''
})

// 表单验证规则
const rules = {
  mailType: [
    { required: true, message: '请选择邮箱类型', trigger: 'change' }
  ],
  importData: [
    { required: true, message: '请输入邮箱数据', trigger: 'blur' },
    { validator: validateImportData, trigger: 'blur' }
  ]
}

// 验证邮箱导入格式
function validateImportData(rule, value, callback) {
  if (!value) {
    callback()
    return
  }
  
  if (formData.mailType === 'outlook') {
    const result = validateOutlookImportData(value)
    if (!result.valid) {
      callback(new Error(result.message))
      return
    }
  }

  callback()
}

// 处理WebSocket导入结果
const handleImportResult = (result) => {
  importResult.value = result
  loading.value = false
  
  if (result.success > 0) {
    ElMessage.success(`成功导入 ${result.success} 个邮箱`)
  } else {
    ElMessage.warning('没有成功导入任何邮箱，请检查导入数据')
  }
  
  // 刷新邮箱列表
  emailsStore.fetchEmails()
}

// 注册和移除WebSocket消息处理器
onMounted(() => {
  WebSocketService.onMessage('import_result', handleImportResult)
})

onUnmounted(() => {
  WebSocketService.offMessage('import_result', handleImportResult)
})

// 提交表单
async function submitForm() {
  if (!formRef.value) return
  
  try {
    await formRef.value.validate()
    loading.value = true
    
    // 准备发送的数据，添加邮箱类型标识
    const importDataWithType = {
      data: formData.importData.trim(),
      mailType: formData.mailType
    }
    
    // 如果WebSocket已连接，则使用WebSocket导入
    if (WebSocketService.isConnected) {
      // 使用WebSocket发送导入请求
      WebSocketService.importEmails(importDataWithType)
      
      ElMessage.info('正在处理导入请求，请稍候...')
      // 结果将通过WebSocket消息回调处理
    } else {
      // 否则使用API导入
      const result = await emailsStore.importEmails(importDataWithType)
      importResult.value = result
      
      if (result.success > 0) {
        ElMessage.success(`成功导入 ${result.success} 个邮箱`)
      } else {
        ElMessage.warning('没有成功导入任何邮箱，请检查导入数据')
      }
    }
  } catch (error) {
    ElMessage.error(error.message || '表单验证失败')
    loading.value = false
  }
}

// 重置表单
function resetForm() {
  if (formRef.value) {
    formRef.value.resetFields()
  }
  importResult.value = null
}

// 获取结果标题
function getResultTitle() {
  if (!importResult.value) return ''
  
  if (importResult.value.success > 0) {
    return `成功导入 ${importResult.value.success} 个邮箱`
  } else {
    return '导入失败'
  }
}

// 获取结果子标题
function getResultSubtitle() {
  if (!importResult.value) return ''
  
  if (importResult.value.failed > 0) {
    return `共处理 ${importResult.value.total} 个记录，${importResult.value.failed} 个失败`
  } else {
    return `共处理 ${importResult.value.total} 个记录，全部成功`
  }
}

// 导航到邮箱列表
function navigateToEmails() {
  router.push('/emails')
}
</script>

<style scoped>
.import-container {
  max-width: 1280px;
  margin: 0 auto;
  padding: 20px;
}

.page-title {
  font-size: 24px;
  margin-bottom: 20px;
  color: #409eff;
}

.import-card {
  margin-bottom: 20px;
}

.import-form {
  margin-bottom: 20px;
}

.import-result {
  margin-top: 20px;
}

.guide-card {
  margin-bottom: 20px;
}

.guide-content {
  line-height: 1.6;
}

.guide-content ol {
  padding-left: 20px;
  margin-bottom: 20px;
}

.guide-content li {
  margin-bottom: 10px;
}

.guide-content a {
  color: #409eff;
  text-decoration: none;
}

.guide-content a:hover {
  text-decoration: underline;
}

@media (max-width: 768px) {
  .import-container {
    padding: 10px;
  }
}
</style> 
