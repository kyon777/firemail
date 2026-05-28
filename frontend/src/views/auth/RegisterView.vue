<template>
  <div class="register-container">
    <div class="register-box">
      <h1 class="title">注册</h1>
      
      <div v-if="error" class="alert alert-danger">
        {{ error }}
      </div>
      
      <form @submit.prevent="handleRegister" class="register-form">
        <div class="form-group">
          <label for="username">用户名</label>
          <input 
            type="text" 
            id="username" 
            v-model="username" 
            class="form-control" 
            placeholder="请输入用户名" 
            required 
            autofocus
          />
          <small class="form-text text-muted">用户名长度应为3-20个字符</small>
        </div>
        
        <div class="form-group">
          <label for="verificationEmail">注册验证邮箱</label>
          <input 
            type="email" 
            id="verificationEmail" 
            v-model.trim="verificationEmail" 
            class="form-control" 
            placeholder="请输入分配给你的邮箱地址" 
            required
          />
          <small class="form-text text-muted">必须填写总邮箱库中已分配的邮箱，仅用于注册资格验证</small>
        </div>
        
        <div class="form-group">
          <label for="password">密码</label>
          <input 
            type="password" 
            id="password" 
            v-model="password" 
            class="form-control" 
            placeholder="请输入密码" 
            required
          />
          <small class="form-text text-muted">密码长度应至少为6个字符</small>
        </div>
        
        <div class="form-group">
          <label for="confirmPassword">确认密码</label>
          <input 
            type="password" 
            id="confirmPassword" 
            v-model="confirmPassword" 
            class="form-control" 
            placeholder="请再次输入密码" 
            required
          />
        </div>
        
        <div class="form-actions">
          <button type="submit" class="btn btn-primary btn-block" :disabled="loading || !formValid">
            <span v-if="loading">注册中...</span>
            <span v-else>注册</span>
          </button>
        </div>
      </form>
      
      <div class="register-footer">
        <p>已有账号? <router-link :to="{ name: 'login' }">登录</router-link></p>
      </div>
    </div>
  </div>
</template>

<script>
import { mapActions } from 'vuex';
import api from '@/services/api';

export default {
  name: 'RegisterView',
  data() {
    return {
      username: '',
      verificationEmail: '',
      password: '',
      confirmPassword: '',
      loading: false,
      error: '',
      registrationEnabled: true  // 默认假设允许注册
    };
  },
  computed: {
    formValid() {
      return this.username.length >= 3 && 
             this.username.length <= 20 && 
             this.verificationEmail.trim().length > 0 &&
             this.password.length >= 6 && 
             this.password === this.confirmPassword;
    }
  },
  methods: {
    ...mapActions('auth', ['register', 'login', 'registerAndLogin']),
    async handleRegister() {
      // 验证表单
      if (!this.formValid) {
        if (this.username.length < 3 || this.username.length > 20) {
          this.error = '用户名长度应为3-20个字符';
        } else if (!this.verificationEmail.trim()) {
          this.error = '注册验证邮箱不能为空';
        } else if (this.password.length < 6) {
          this.error = '密码长度应至少为6个字符';
        } else if (this.password !== this.confirmPassword) {
          this.error = '两次输入的密码不一致';
        }
        return;
      }
      
      this.loading = true;
      this.error = '';
      
      try {
        // 检查是否允许注册
        if (!this.registrationEnabled) {
          throw new Error('系统当前不允许注册新用户，请联系管理员');
        }
        
        console.log('开始注册流程，用户名:', this.username);
        
        // 使用新的注册并自动登录方法
        const result = await this.registerAndLogin({
          username: this.username,
          password: this.password,
          verificationEmail: this.verificationEmail.trim()
        });
        
        if (result.success) {
          // 注册和登录都成功
          console.log('注册和登录成功');
          this.$router.push('/');
        } else {
          // 注册成功但登录失败
          console.warn('注册成功但登录失败:', result.message);
          this.$router.push({ 
            name: 'login',
            params: { 
              registrationSuccess: true,
              loginAttemptFailed: true
            }
          });
        }
      } catch (error) {
        console.error('注册失败:', error);
        this.error = error.response?.data?.error || error.message || '注册失败，请稍后再试';
      } finally {
        this.loading = false;
      }
    },
    
    async checkRegistrationStatus() {
      try {
        console.log('开始检查注册功能状态...');
        const response = await api.getConfig();
        console.log('获取到系统配置:', response.data);
        
        // 明确处理allow_register为undefined或null的情况
        if (response.data && response.data.allow_register === false) {
          this.registrationEnabled = false;
          this.error = '系统当前不允许注册新用户，请联系管理员';
          console.log('注册功能已关闭');
        } else {
          // 其他所有情况都允许注册
          this.registrationEnabled = true;
          this.error = '';
          console.log('注册功能已开启');
        }
      } catch (error) {
        console.error('获取注册状态失败:', error);
        // 获取配置失败时，默认允许注册
        this.registrationEnabled = true;
        this.error = '';
        console.log('配置获取失败，默认允许注册');
        
        // 尝试再次获取配置（后台静默重试）
        setTimeout(() => {
          console.log('尝试再次获取注册状态...');
          api.getConfig()
            .then(response => {
              console.log('重试获取配置成功:', response.data);
              // 仅当明确禁用时更新状态
              if (response.data && response.data.allow_register === false) {
                this.registrationEnabled = false;
                this.error = '系统当前不允许注册新用户，请联系管理员';
                console.log('更新注册状态: 已禁用');
              }
            })
            .catch(err => {
              console.error('重试获取注册状态失败:', err);
              // 保持默认允许注册
            });
        }, 3000); // 3秒后重试
      }
    }
  },
  mounted() {
    this.checkRegistrationStatus();
  }
};
</script>

<style scoped>
.register-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 80px);
  padding: 20px;
}

.register-box {
  width: 100%;
  max-width: 400px;
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  padding: 30px;
}

.title {
  text-align: center;
  margin-bottom: 24px;
  color: #333;
  font-weight: 600;
}

.register-form {
  margin-bottom: 20px;
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

.btn-primary {
  background-color: #42b983;
  color: white;
}

.btn-primary:hover {
  background-color: #3aa876;
}

.btn-block {
  display: block;
  width: 100%;
}

.btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.form-actions {
  margin-top: 30px;
}

.register-footer {
  text-align: center;
  margin-top: 20px;
  color: #666;
}

.register-footer a {
  color: #42b983;
  text-decoration: none;
}

.register-footer a:hover {
  text-decoration: underline;
}

.alert {
  padding: 12px;
  border-radius: 4px;
  margin-bottom: 20px;
}

.alert-danger {
  background-color: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}
</style> 
