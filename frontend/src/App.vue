<template>
  <el-config-provider :locale="zhCn">
    <div class="app-container">
      <el-container>
        <el-header class="app-header" :class="{ 'scrolled': isScrolled }">
          <div class="header-left">
            <router-link to="/" class="logo-link">
              <h1>花火邮箱助手</h1>
            </router-link>
          </div>

          <div class="header-right">
            <!-- 用户未登录状态 -->
            <template v-if="!isAuthenticated">
              <router-link to="/login">
                <el-button type="primary" plain>登录</el-button>
              </router-link>
              <router-link to="/register">
                <el-button type="primary">注册</el-button>
              </router-link>
            </template>

            <!-- 用户已登录状态 -->
            <template v-else>
              <el-dropdown @command="handleUserCommand">
                <span class="user-dropdown-link">
                  {{ currentUser ? currentUser.username : '用户' }}
                  <el-icon><arrow-down /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="account">账户设置</el-dropdown-item>
                    <el-dropdown-item v-if="isAdmin" command="admin">用户管理</el-dropdown-item>
                    <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>

            <div class="connection-status">
              <el-tag :type="websocketConnected ? 'success' : 'danger'" effect="dark">
                {{ websocketConnected ? '已连接' : '未连接' }}
              </el-tag>
            </div>
          </div>
        </el-header>

        <!-- 导航菜单 -->
        <el-menu
          v-if="isAuthenticated"
          mode="horizontal"
          :router="true"
          :default-active="$route.path"
          class="app-nav"
        >
          <el-menu-item index="/">
            <el-icon><HomeFilled /></el-icon>首页
          </el-menu-item>
          <el-menu-item index="/emails">
            <el-icon><Message /></el-icon>邮箱管理
          </el-menu-item>
          <el-menu-item index="/import">
            <el-icon><Upload /></el-icon>批量导入
          </el-menu-item>
          <el-menu-item index="/search">
            <el-icon><Search /></el-icon>邮件搜索
          </el-menu-item>
          <el-menu-item index="/admin/users" v-if="isAdmin">
            <el-icon><UserFilled /></el-icon>用户管理
          </el-menu-item>
          <el-menu-item index="/about">
            <el-icon><InfoFilled /></el-icon>关于
          </el-menu-item>
        </el-menu>

        <el-main>
          <router-view v-slot="{ Component }" v-if="!initializing">
            <transition name="fade" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
          <div v-else class="loading-container">
            <el-skeleton :rows="6" animated />
          </div>
        </el-main>

        <el-footer class="app-footer">
          花火邮箱助手 &copy; 2025
        </el-footer>
      </el-container>

      <!-- 通知组件 -->
      <Notifications />

      <!-- 调试工具 -->
      <div v-if="showDebugTools" class="debug-tools-container">
        <DebugTools />
      </div>

      <!-- 调试工具开关 -->
      <div class="debug-tools-toggle" @click="toggleDebugTools">
        <el-tooltip content="调试工具" placement="left">
          <el-button type="primary" circle size="small">
            <el-icon><Setting /></el-icon>
          </el-button>
        </el-tooltip>
      </div>
    </div>
  </el-config-provider>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useStore } from 'vuex'
import { ElConfigProvider, ElMessage } from 'element-plus'
import { ArrowDown, Search, Message, HomeFilled, InfoFilled, UserFilled, Setting, Upload } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import websocket from '@/services/websocket'
import Notifications from './components/Notifications.vue'
import DebugTools from './components/DebugTools.vue'

// 初始化状态
const initializing = ref(true)
const isConnected = ref(false)
const isScrolled = ref(false)
const showDebugTools = ref(false)

// 使用Vuex来管理状态
const store = useStore()
const router = useRouter()

// 计算属性
const websocketConnected = computed(() => store.state.websocketConnected)
const isAuthenticated = computed(() => store.getters['auth/isAuthenticated'])
const currentUser = computed(() => store.getters['auth/currentUser'])
const isAdmin = computed(() => {
  const adminStatus = store.getters['auth/isAdmin']
  console.log('管理员状态检查:', adminStatus, '当前用户:', store.getters['auth/currentUser'])
  return adminStatus
})

// 监听滚动事件
const handleScroll = () => {
  isScrolled.value = window.scrollY > 10
}

// 切换调试工具显示
const toggleDebugTools = () => {
  showDebugTools.value = !showDebugTools.value
  // 保存状态到localStorage
  localStorage.setItem('show_debug_tools', showDebugTools.value ? 'true' : 'false')
}

// 初始化认证状态
const initializeAuth = async () => {
  initializing.value = true

  if (isAuthenticated.value) {
    try {
      // 强制获取当前用户最新信息
      console.log('初始化认证状态 - 获取最新用户信息')
      await store.dispatch('auth/getCurrentUser')
      console.log('用户信息更新完成，当前用户:', currentUser.value, '管理员状态:', isAdmin.value)
    } catch (error) {
      console.error('获取用户信息失败:', error)
    }
  } else {
    console.log('用户未认证，跳过获取用户信息')
  }

  initializing.value = false
}

// 用户下拉菜单命令处理
const handleUserCommand = (command) => {
  switch (command) {
    case 'account':
      router.push('/account')
      break
    case 'admin':
      router.push('/admin/users')
      break
    case 'logout':
      handleLogout()
      break
  }
}

// 退出登录
const handleLogout = async () => {
  try {
    await store.dispatch('auth/logout')
    router.push('/login')
    ElMessage({
      type: 'success',
      message: '已成功退出登录'
    })
  } catch (error) {
    console.error('登出失败:', error)
    ElMessage.error('退出登录失败')
  }
}

// 更新连接状态
const updateConnectionStatus = () => {
  isConnected.value = websocket.isConnected
}

// 监听WebSocket连接变化
const handleConnect = () => {
  store.commit('SET_WEBSOCKET_CONNECTED', true)
}

const handleDisconnect = () => {
  store.commit('SET_WEBSOCKET_CONNECTED', false)
}

// 监听认证状态变化
watch(isAuthenticated, (newValue) => {
  // 认证状态发生变化时，重新处理WebSocket连接
  if (newValue) {
    if (!websocket.isConnected) {
      websocket.connect()
    }
  } else {
    websocket.disconnect()
  }
})

// 组件挂载时连接WebSocket和初始化认证
onMounted(async () => {
  // 初始化认证状态
  await initializeAuth()

  // 连接处理
  websocket.onConnect(() => {
    isConnected.value = true
  })

  // 断开连接处理
  websocket.onDisconnect(() => {
    isConnected.value = false
  })

  // 注册WebSocket事件处理器
  websocket.onConnect(handleConnect)
  websocket.onDisconnect(handleDisconnect)

  // 确保WebSocket连接（仅在用户已认证时）
  if (isAuthenticated.value && !websocket.isConnected) {
    websocket.connect()
  }

  // 添加滚动监听
  window.addEventListener('scroll', handleScroll)

  // 初始化调试工具状态
  showDebugTools.value = localStorage.getItem('show_debug_tools') === 'true'

  // 设置Cookie策略
  if (!document.cookie.includes('CookieConsent')) {
    document.cookie = "CookieConsent=true; SameSite=None; Secure; Partitioned; Path=/;";
  }
})

// 组件卸载时断开WebSocket连接
onUnmounted(() => {
  websocket.offConnect(handleConnect)
  websocket.offDisconnect(handleDisconnect)
  websocket.disconnect()

  // 移除滚动监听
  window.removeEventListener('scroll', handleScroll)
})
</script>

<style>
/* 全局样式 */
:root {
  --primary-color: #3B82F6;
  --success-color: #22C55E;
  --warning-color: #F59E0B;
  --danger-color: #EF4444;
  --info-color: #64748B;
  --text-color: #1E293B;
  --border-color: #E2E8F0;
  --background-color: #F8FAFC;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
  color: var(--text-color);
  background-color: var(--background-color);
  line-height: 1.5;
  min-height: 100vh;
}

.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.el-container {
  flex: 1;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.el-main {
  flex: 1;
  padding: 20px;
  background-color: var(--background-color);
}

.app-header {
  background-color: white;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  height: 60px !important;
  box-shadow: var(--box-shadow-sm);
  position: sticky;
  top: 0;
  z-index: 10;
  transition: all var(--transition-normal);
}

.app-header.scrolled {
  box-shadow: var(--box-shadow);
}

.header-left {
  display: flex;
  align-items: center;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.app-header h1 {
  font-size: 22px;
  color: var(--primary-color);
  margin: 0;
  font-weight: 600;
  letter-spacing: -0.5px;
  position: relative;
}

.app-header h1::after {
  content: '';
  position: absolute;
  bottom: -4px;
  left: 0;
  width: 30px;
  height: 2px;
  background-color: var(--primary-color);
  border-radius: var(--border-radius-full);
  transition: width var(--transition-normal);
}

.app-header h1:hover::after {
  width: 100%;
}

.connection-status {
  display: flex;
  align-items: center;
  margin-left: 16px;
}

.user-dropdown-link {
  display: flex;
  align-items: center;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-color);
  padding: 6px 12px;
  border-radius: var(--border-radius);
  transition: background-color var(--transition-fast);
}

.user-dropdown-link:hover {
  background-color: var(--border-color-lighter);
}

.user-dropdown-link .el-icon {
  margin-left: 4px;
  transition: transform var(--transition-fast);
}

.user-dropdown-link:hover .el-icon {
  transform: rotate(180deg);
}

.app-nav {
  border-bottom: 1px solid var(--border-color);
  box-shadow: var(--box-shadow-sm);
  background-color: white;
}

.app-nav .el-menu-item {
  transition: all var(--transition-normal);
  border-bottom: 2px solid transparent;
}

.app-nav .el-menu-item.is-active {
  color: var(--primary-color);
  border-bottom-color: var(--primary-color);
}

.app-nav .el-menu-item:hover {
  background-color: var(--border-color-lighter);
}

.app-nav .el-icon {
  margin-right: 4px;
}

.app-footer {
  text-align: center;
  color: var(--info-color);
  font-size: 14px;
  padding: 20px 0 !important;
  background-color: white;
  border-top: 1px solid var(--border-color);
  margin-top: auto;
}

.loading-container {
  padding: 40px 0;
}

/* 添加页面过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 按钮和标签样式增强 */
.el-button {
  border-radius: var(--border-radius);
  transition: all var(--transition-fast);
}

.el-button:hover {
  transform: translateY(-1px);
  box-shadow: var(--box-shadow-sm);
}

.el-tag {
  border-radius: var(--border-radius-full);
  padding: 0 10px;
  height: 24px;
  line-height: 22px;
  font-size: 12px;
}

/* 表单元素样式 */
.el-input__inner,
.el-textarea__inner {
  border-radius: var(--border-radius);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.el-input__inner:focus,
.el-textarea__inner:focus {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

/* 响应式布局 */
@media (max-width: 768px) {
  .header-right {
    gap: 8px;
  }

  .app-header h1 {
    font-size: 18px;
  }

  .connection-status {
    margin-left: 8px;
  }

  .app-nav .el-menu-item {
    padding: 0 10px;
  }
}

@media (max-width: 576px) {
  .header-right {
    flex-direction: column;
    align-items: flex-end;
  }

  .connection-status {
    margin-top: 10px;
    margin-left: 0;
  }

  .app-nav .el-menu-item {
    padding: 0 8px;
    font-size: 14px;
  }

  .app-nav .el-icon {
    margin-right: 2px;
    font-size: 14px;
  }

  .debug-tools-container {
    width: 90vw;
    right: 5vw;
  }
}

/* 调试工具样式 */
.debug-tools-container {
  position: fixed;
  bottom: 60px;
  right: 20px;
  width: 400px;
  max-width: 90vw;
  z-index: 2000;
  background-color: white;
  border-radius: var(--border-radius);
  box-shadow: var(--box-shadow);
  transition: all var(--transition-normal);
}

.debug-tools-toggle {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 2001;
  cursor: pointer;
  transition: all var(--transition-normal);
}

.debug-tools-toggle:hover {
  transform: rotate(45deg);
}
</style>
