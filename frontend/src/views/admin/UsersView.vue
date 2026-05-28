<template>
  <div class="users-container">
    <div class="users-header">
      <h1>用户管理</h1>
      <div class="header-actions">
        <div class="registration-toggle">
          <span>注册功能：</span>
          <el-switch
            v-model="registrationEnabled"
            active-text="开启"
            inactive-text="关闭"
            @change="toggleRegistration"
          />
        </div>
        <button class="btn btn-primary" @click="showAddUserModal = true">添加用户</button>
      </div>
    </div>

    <div class="alert-container">
      <div v-if="message" :class="['alert', message.type === 'success' ? 'alert-success' : 'alert-danger']">
        {{ message.text }}
      </div>
    </div>

    <div class="users-list-container">
      <div v-if="loading" class="loading-spinner">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>

      <table v-else class="users-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>用户名</th>
            <th>类型</th>
            <th>邮箱数量</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="users.length === 0">
            <td colspan="6" class="text-center">暂无用户数据</td>
          </tr>
          <tr v-for="user in users" :key="user.id">
            <td>{{ user.id }}</td>
            <td>{{ user.username }}</td>
            <td>{{ user.is_admin ? '管理员' : '普通用户' }}</td>
            <td>
              <button
                class="btn btn-sm btn-info"
                @click="openUserEmailsModal(user)"
                :disabled="(user.email_count || 0) === 0"
              >
                查看邮箱 ({{ user.email_count || 0 }})
              </button>
            </td>
            <td>{{ formatDate(user.created_at) }}</td>
            <td class="actions">
              <button
                class="btn btn-sm btn-warning"
                @click="openResetPasswordModal(user)"
                :disabled="user.id === currentUser.id"
              >
                重置密码
              </button>
              <button
                class="btn btn-sm btn-danger"
                @click="openDeleteUserModal(user)"
                :disabled="user.id === currentUser.id"
              >
                删除
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 用户邮箱列表模态框 -->
    <div v-if="showUserEmailsModal" class="modal-overlay">
      <div class="modal-container modal-lg">
        <div class="modal-header">
          <h2>用户邮箱列表 - {{ selectedUser?.username }}</h2>
          <button class="modal-close" @click="closeUserEmailsModal">&times;</button>
        </div>
        <div class="modal-body">
          <p class="text-muted">仅展示邮箱摘要，不展示密码、Refresh Token、Client ID。</p>

          <table class="email-summary-table" v-if="selectedUserEmails.length > 0">
            <thead>
              <tr>
                <th>ID</th>
                <th>邮箱</th>
                <th>类型</th>
                <th>导入/绑定时间</th>
                <th>最后检查时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="email in selectedUserEmails" :key="email.id">
                <td>{{ email.id }}</td>
                <td>{{ email.email }}</td>
                <td>{{ email.mail_type || '未知' }}</td>
                <td>{{ formatDate(email.created_at) }}</td>
                <td>{{ formatDate(email.last_check_time) }}</td>
                <td>
                  <button
                    class="btn btn-sm btn-primary"
                    @click="openEmailRecordsPanel(email)"
                  >
                    查看邮件
                  </button>
                </td>
              </tr>
            </tbody>
          </table>

          <div v-if="selectedEmailForRecords" class="mail-records-panel">
            <div class="records-header">
              <h3>邮件记录 - {{ selectedEmailForRecords.email }}</h3>
              <button class="btn btn-sm btn-secondary" @click="closeEmailRecordsPanel">收起</button>
            </div>
            <div v-if="mailRecordsLoading" class="text-center text-muted">邮件记录加载中...</div>
            <div v-else-if="mailRecordsError" class="alert alert-danger">{{ mailRecordsError }}</div>
            <div v-else-if="selectedEmailRecords.length === 0" class="text-center text-muted">该邮箱暂无邮件记录</div>
            <div v-else class="mail-records-list">
              <div v-for="record in selectedEmailRecords" :key="record.id" class="mail-record-card">
                <div class="mail-record-title">{{ record.subject || '无主题' }}</div>
                <div class="mail-record-meta">
                  <span>发件人：{{ record.sender || '未知' }}</span>
                  <span>文件夹：{{ record.folder || '未知' }}</span>
                  <span>时间：{{ formatDate(record.received_time) }}</span>
                </div>
                <pre class="mail-record-content">{{ formatMailContent(record.content) }}</pre>
              </div>
            </div>
          </div>

          <p v-if="selectedUserEmails.length === 0" class="text-center">该用户暂无邮箱</p>

          <div class="form-actions">
            <button type="button" class="btn btn-secondary" @click="closeUserEmailsModal">关闭</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加用户模态框 -->
    <div v-if="showAddUserModal" class="modal-overlay">
      <div class="modal-container">
        <div class="modal-header">
          <h2>添加新用户</h2>
          <button class="modal-close" @click="showAddUserModal = false">&times;</button>
        </div>
        <div class="modal-body">
          <div v-if="addUserError" class="alert alert-danger">
            {{ addUserError }}
          </div>

          <form @submit.prevent="handleAddUser">
            <div class="form-group">
              <label for="newUsername">用户名</label>
              <input
                type="text"
                id="newUsername"
                v-model="newUser.username"
                class="form-control"
                placeholder="请输入用户名"
                required
              />
              <small class="form-text text-muted">用户名长度应为3-20个字符</small>
            </div>

            <div class="form-group">
              <label for="newPassword">密码</label>
              <input
                type="password"
                id="newPassword"
                v-model="newUser.password"
                class="form-control"
                placeholder="请输入密码"
                required
              />
              <small class="form-text text-muted">密码长度应至少为6个字符</small>
            </div>

            <div class="form-group">
              <label>
                <input type="checkbox" v-model="newUser.is_admin" /> 管理员权限
              </label>
            </div>

            <div class="form-actions">
              <button type="button" class="btn btn-secondary" @click="showAddUserModal = false">取消</button>
              <button type="submit" class="btn btn-primary" :disabled="addUserLoading || !newUserFormValid">
                <span v-if="addUserLoading">添加中...</span>
                <span v-else>添加用户</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <!-- 重置密码模态框 -->
    <div v-if="showResetPasswordModal" class="modal-overlay">
      <div class="modal-container">
        <div class="modal-header">
          <h2>重置用户密码</h2>
          <button class="modal-close" @click="showResetPasswordModal = false">&times;</button>
        </div>
        <div class="modal-body">
          <div v-if="resetPasswordError" class="alert alert-danger">
            {{ resetPasswordError }}
          </div>

          <form @submit.prevent="handleResetPassword">
            <div class="form-group">
              <label for="newPasswordInput">新密码</label>
              <input
                type="password"
                id="newPasswordInput"
                v-model="resetPasswordData.newPassword"
                class="form-control"
                placeholder="请输入新密码"
                required
              />
              <small class="form-text text-muted">密码长度应至少为6个字符</small>
            </div>

            <div class="form-group">
              <label for="confirmPasswordInput">确认密码</label>
              <input
                type="password"
                id="confirmPasswordInput"
                v-model="resetPasswordData.confirmPassword"
                class="form-control"
                placeholder="请再次输入新密码"
                required
              />
            </div>

            <div class="form-actions">
              <button type="button" class="btn btn-secondary" @click="showResetPasswordModal = false">取消</button>
              <button type="submit" class="btn btn-primary" :disabled="resetPasswordLoading || !resetPasswordFormValid">
                <span v-if="resetPasswordLoading">重置中...</span>
                <span v-else>重置密码</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <!-- 删除用户模态框 -->
    <div v-if="showDeleteUserModal" class="modal-overlay">
      <div class="modal-container">
        <div class="modal-header">
          <h2>删除用户</h2>
          <button class="modal-close" @click="showDeleteUserModal = false">&times;</button>
        </div>
        <div class="modal-body">
          <div v-if="deleteUserError" class="alert alert-danger">
            {{ deleteUserError }}
          </div>

          <p>您确定要删除用户 <strong>{{ selectedUser?.username }}</strong> 吗？</p>
          <p class="text-danger">此操作不可逆，用户所有数据将被永久删除。</p>

          <div class="form-actions">
            <button type="button" class="btn btn-secondary" @click="showDeleteUserModal = false">取消</button>
            <button
              type="button"
              class="btn btn-danger"
              @click="handleDeleteUser"
              :disabled="deleteUserLoading"
            >
              <span v-if="deleteUserLoading">删除中...</span>
              <span v-else>确认删除</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import api from '@/services/api'

export default {
  name: 'UsersView',
  data() {
    return {
      users: [],
      loading: false,
      message: null,
      messageTimeout: null,
      registrationEnabled: false,

      // 当前用户
      currentUser: {
        id: null,
        username: '',
        is_admin: false
      },

      // 添加用户
      showAddUserModal: false,
      newUser: {
        username: '',
        password: '',
        is_admin: false
      },
      addUserLoading: false,
      addUserError: null,

      // 重置密码
      showResetPasswordModal: false,
      selectedUser: null,
      showUserEmailsModal: false,
      selectedUserEmails: [],
      selectedEmailForRecords: null,
      selectedEmailRecords: [],
      mailRecordsLoading: false,
      mailRecordsError: null,
      resetPasswordData: {
        newPassword: '',
        confirmPassword: ''
      },
      resetPasswordLoading: false,
      resetPasswordError: null,

      // 删除用户
      showDeleteUserModal: false,
      deleteUserLoading: false,
      deleteUserError: null
    };
  },
  computed: {
    newUserFormValid() {
      return this.newUser.username.length >= 3 &&
             this.newUser.username.length <= 20 &&
             this.newUser.password.length >= 6;
    },
    resetPasswordFormValid() {
      return this.resetPasswordData.newPassword.length >= 6 &&
             this.resetPasswordData.newPassword === this.resetPasswordData.confirmPassword;
    }
  },
  methods: {
    formatDate(dateString) {
      if (!dateString) return '未知';

      const date = new Date(dateString);
      return new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      }).format(date);
    },

    showMessage(type, text, duration = 3000) {
      this.message = { type, text };

      if (this.messageTimeout) {
        clearTimeout(this.messageTimeout);
      }

      this.messageTimeout = setTimeout(() => {
        this.message = null;
      }, duration);
    },

    async fetchUsers() {
      this.loading = true;

      try {
        // 使用api对象调用，确保使用正确的基础URL
        const response = await this.$store.dispatch('auth/getAllUsers');
        this.users = response;
      } catch (error) {
        this.showMessage('error', '获取用户列表失败: ' + (error.message || '未知错误'));
      } finally {
        this.loading = false;
      }
    },

    async fetchSystemConfig() {
      try {
        // 使用api对象调用，确保使用正确的基础URL
        const response = await this.$store.dispatch('auth/getConfig');
        if (response) {
          this.registrationEnabled = response.allow_register;
        }
      } catch (error) {
        console.error('获取系统配置失败', error);
      }
    },

    async toggleRegistration(value) {
      try {
        // 使用api对象调用，确保使用正确的基础URL
        await this.$store.dispatch('auth/toggleRegistration', value);
        this.showMessage('success', `已${value ? '开启' : '关闭'}注册功能`);
      } catch (error) {
        this.registrationEnabled = !value; // 恢复原状态
        this.showMessage('error', `${value ? '开启' : '关闭'}注册功能失败: ${error.message || '未知错误'}`);
      }
    },

    openUserEmailsModal(user) {
      this.selectedUser = user;
      this.selectedUserEmails = Array.isArray(user.emails) ? user.emails : [];
      this.closeEmailRecordsPanel();
      this.showUserEmailsModal = true;
    },

    closeUserEmailsModal() {
      this.showUserEmailsModal = false;
      this.selectedUser = null;
      this.selectedUserEmails = [];
      this.closeEmailRecordsPanel();
    },

    async openEmailRecordsPanel(email) {
      this.selectedEmailForRecords = email;
      this.selectedEmailRecords = [];
      this.mailRecordsError = null;
      this.mailRecordsLoading = true;

      try {
        const response = await api.getMailRecords(email.id);
        this.selectedEmailRecords = Array.isArray(response.data) ? response.data : [];
      } catch (error) {
        this.mailRecordsError = error?.response?.data?.error || error.message || '获取邮件记录失败';
      } finally {
        this.mailRecordsLoading = false;
      }
    },

    closeEmailRecordsPanel() {
      this.selectedEmailForRecords = null;
      this.selectedEmailRecords = [];
      this.mailRecordsLoading = false;
      this.mailRecordsError = null;
    },

    formatMailContent(content) {
      if (!content) return '';
      if (typeof content === 'string') return content;
      if (content.text) return content.text;
      if (content.html) return content.html;
      return JSON.stringify(content, null, 2);
    },

    // 添加用户
    async handleAddUser() {
      if (!this.newUserFormValid) {
        if (this.newUser.username.length < 3 || this.newUser.username.length > 20) {
          this.addUserError = '用户名长度应为3-20个字符';
        } else if (this.newUser.password.length < 6) {
          this.addUserError = '密码长度应至少为6个字符';
        }
        return;
      }

      this.addUserLoading = true;
      this.addUserError = null;

      try {
        // 使用api对象调用，确保使用正确的基础URL
        await this.$store.dispatch('auth/createUser', {
          username: this.newUser.username,
          password: this.newUser.password,
          is_admin: this.newUser.is_admin
        });

        // 刷新用户列表
        await this.fetchUsers();

        // 关闭模态框并重置表单
        this.showAddUserModal = false;
        this.newUser = {
          username: '',
          password: '',
          is_admin: false
        };

        this.showMessage('success', '用户创建成功');
      } catch (error) {
        this.addUserError = error.message || '创建用户失败';
      } finally {
        this.addUserLoading = false;
      }
    },

    // 重置密码
    openResetPasswordModal(user) {
      this.selectedUser = user;
      this.resetPasswordData = {
        newPassword: '',
        confirmPassword: ''
      };
      this.resetPasswordError = null;
      this.showResetPasswordModal = true;
    },

    async handleResetPassword() {
      if (!this.resetPasswordFormValid) {
        if (this.resetPasswordData.newPassword.length < 6) {
          this.resetPasswordError = '密码长度应至少为6个字符';
        } else if (this.resetPasswordData.newPassword !== this.resetPasswordData.confirmPassword) {
          this.resetPasswordError = '两次输入的密码不一致';
        }
        return;
      }

      this.resetPasswordLoading = true;
      this.resetPasswordError = null;

      try {
        // 使用api对象调用，确保使用正确的基础URL
        await this.$store.dispatch('auth/resetUserPassword', {
          userId: this.selectedUser.id,
          newPassword: this.resetPasswordData.newPassword
        });

        // 关闭模态框
        this.showResetPasswordModal = false;
        this.selectedUser = null;

        this.showMessage('success', '用户密码重置成功');
      } catch (error) {
        this.resetPasswordError = error.message || '重置密码失败';
      } finally {
        this.resetPasswordLoading = false;
      }
    },

    // 删除用户
    openDeleteUserModal(user) {
      this.selectedUser = user;
      this.deleteUserError = null;
      this.showDeleteUserModal = true;
    },

    async handleDeleteUser() {
      this.deleteUserLoading = true;
      this.deleteUserError = null;

      try {
        // 使用api对象调用，确保使用正确的基础URL
        await this.$store.dispatch('auth/deleteUser', this.selectedUser.id);

        // 刷新用户列表
        await this.fetchUsers();

        // 关闭模态框
        this.showDeleteUserModal = false;
        this.selectedUser = null;

        this.showMessage('success', '用户删除成功');
      } catch (error) {
        this.deleteUserError = error.message || '删除用户失败';
      } finally {
        this.deleteUserLoading = false;
      }
    },

    // 获取当前用户信息
    async fetchCurrentUser() {
      try {
        // 使用api对象调用，确保使用正确的基础URL
        const response = await this.$store.dispatch('auth/getCurrentUser');
        if (response) {
          this.currentUser = {
            id: response.id,
            username: response.username,
            is_admin: response.isAdmin
          };
        }
      } catch (error) {
        console.error('获取当前用户信息失败:', error);
      }
    }
  },
  mounted() {
    this.fetchCurrentUser();
    this.fetchUsers();
    this.fetchSystemConfig();
  },
  beforeUnmount() {
    // 清除消息定时器
    if (this.messageTimeout) {
      clearTimeout(this.messageTimeout);
    }
  }
};
</script>

<style scoped>
.users-container {
  min-height: calc(100vh - 160px); /* 减去header和footer的高度 */
  display: flex;
  flex-direction: column;
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.users-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.users-header h1 {
  font-size: 28px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 20px;
}

.registration-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
}

.alert-container {
  margin-bottom: 20px;
}

.users-list-container {
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  padding: 20px;
  overflow-x: auto;
}

.users-table {
  width: 100%;
  border-collapse: collapse;
}

.users-table th,
.users-table td {
  padding: 12px 15px;
  text-align: left;
  border-bottom: 1px solid #eee;
}

.users-table th {
  font-weight: 600;
  color: #333;
  background-color: #f8f8f8;
}

.users-table tbody tr:hover {
  background-color: #f9f9f9;
}

.text-center {
  text-align: center;
}

.actions {
  display: flex;
  gap: 8px;
}

.btn {
  display: inline-block;
  padding: 10px 20px;
  font-size: 16px;
  font-weight: 500;
  text-align: center;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s, opacity 0.3s;
  border: none;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 14px;
}

.btn-primary {
  background-color: #42b983;
  color: white;
}

.btn-primary:hover {
  background-color: #3aa876;
}

.btn-secondary {
  background-color: #6c757d;
  color: white;
}

.btn-secondary:hover {
  background-color: #5a6268;
}

.btn-warning {
  background-color: #ffc107;
  color: #212529;
}

.btn-warning:hover {
  background-color: #e0a800;
}

.btn-info {
  background-color: #17a2b8;
  color: white;
}

.btn-info:hover {
  background-color: #138496;
}

.btn-danger {
  background-color: #dc3545;
  color: white;
}

.btn-danger:hover {
  background-color: #c82333;
}

.btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.alert {
  padding: 12px;
  border-radius: 4px;
  margin-bottom: 20px;
}

.alert-success {
  background-color: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.alert-danger {
  background-color: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

.loading-spinner {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 0;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #42b983;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 10px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* 模态框样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-container {
  background-color: #fff;
  border-radius: 8px;
  width: 100%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.modal-lg {
  max-width: 900px;
}

.email-summary-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 12px;
}

.email-summary-table th,
.email-summary-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid #eee;
  word-break: break-all;
}

.email-summary-table th {
  background-color: #f8f8f8;
  font-weight: 600;
}

.mail-records-panel {
  margin-top: 18px;
  padding: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafafa;
}

.records-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.records-header h3 {
  margin: 0;
  font-size: 18px;
}

.mail-records-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 420px;
  overflow-y: auto;
}

.mail-record-card {
  padding: 12px;
  border: 1px solid #eee;
  border-radius: 6px;
  background: #fff;
}

.mail-record-title {
  font-weight: 600;
  margin-bottom: 8px;
  color: #333;
}

.mail-record-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.mail-record-content {
  max-height: 180px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  padding: 10px;
  border-radius: 4px;
  background: #f5f5f5;
  font-size: 13px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 20px;
  border-bottom: 1px solid #eee;
}

.modal-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #666;
}

.modal-body {
  padding: 20px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 16px;
  transition: border-color 0.3s;
}

.form-control:focus {
  border-color: #42b983;
  outline: none;
}

.form-text {
  display: block;
  margin-top: 5px;
  font-size: 12px;
}

.text-muted {
  color: #6c757d;
}

.text-danger {
  color: #dc3545;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 30px;
}
</style>
