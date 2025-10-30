<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h2>登录 Kahuna-System</h2>
        <p>请输入您的账号信息</p>
      </div>
      
      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        class="login-form"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="用户名"
            size="large"
            prefix-icon="User"
            @keyup.enter="focusPassword"
          />
        </el-form-item>
        
        <el-form-item prop="password">
          <el-input
            ref="passwordInputRef"
            v-model="loginForm.password"
            type="password"
            placeholder="密码"
            size="large"
            prefix-icon="Lock"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-button"
            :loading="authStore.isLoading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>
      
      <div class="register-link">
        <el-button
          type="text"
          size="default"
          @click="showRegisterDialog = true"
        >
          还没有账号？立即注册
        </el-button>
      </div>
      
      <div v-if="authStore.error" class="error-message">
        {{ authStore.error }}
      </div>
    </div>
    
    <!-- 注册对话框 -->
    <el-dialog
      v-model="showRegisterDialog"
      title="注册账号"
      width="400px"
      :close-on-click-modal="false"
      @close="handleDialogClose"
    >
      <el-form
        ref="registerFormRef"
        :model="registerForm"
        :rules="registerRules"
        label-width="80px"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="registerForm.username"
            placeholder="请输入用户名（仅支持字母和数字）"
            size="large"
          />
        </el-form-item>
        
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="registerForm.password"
            type="password"
            placeholder="请输入密码（至少6位）"
            size="large"
            show-password
          />
        </el-form-item>
        
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="registerForm.confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            size="large"
            show-password
          />
        </el-form-item>
        
        <el-form-item label="邀请码" prop="inviteCode">
          <el-input
            v-model="registerForm.inviteCode"
            placeholder="请输入邀请码"
            size="large"
          />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="showRegisterDialog = false">取消</el-button>
          <el-button
            type="primary"
            :loading="isRegistering"
            @click="handleRegister"
          >
            确定
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()
const passwordInputRef = ref<HTMLElement>()

const showRegisterDialog = ref(false)
const isRegistering = ref(false)

const loginForm = reactive({
  username: '',
  password: ''
})

const registerForm = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  inviteCode: ''
})

// 验证用户名格式（只能包含字母和数字）
const validateUsername = (rule: any, value: string, callback: any) => {
  if (!value) {
    callback(new Error('请输入用户名'))
  } else if (!/^[a-zA-Z0-9]+$/.test(value)) {
    callback(new Error('用户名只能包含大小写字母和数字'))
  } else {
    callback()
  }
}

// 验证确认密码
const validateConfirmPassword = (rule: any, value: string, callback: any) => {
  if (!value) {
    callback(new Error('请再次输入密码'))
  } else if (value !== registerForm.password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const loginRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' }
  ]
}

const registerRules: FormRules = {
  username: [
    { required: true, validator: validateUsername, trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度至少为6位', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, validator: validateConfirmPassword, trigger: 'blur' }
  ],
  inviteCode: [
    { required: true, message: '请输入邀请码', trigger: 'blur' }
  ]
}

// 用户名输入框回车时，聚焦到密码框
const focusPassword = () => {
  if (passwordInputRef.value) {
    passwordInputRef.value.focus()
  }
}

// 密码输入框回车时，执行登录
const handleLogin = async () => {
  if (!loginFormRef.value) return
  
  try {
    await loginFormRef.value.validate()
    const result = await authStore.login(loginForm)
  
    if (result.success) {
      ElMessage.success('登录成功')
      router.push('/')
    } else {
      ElMessage.error(result.error || '登录失败')
    }
  } catch (error) {
    console.error('表单验证失败:', error)
  }
}

// 处理注册
const handleRegister = async () => {
  if (!registerFormRef.value) return
  
  try {
    await registerFormRef.value.validate()
    isRegistering.value = true
    
    const response = await fetch('/api/auth/signup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        username: registerForm.username,
        password: registerForm.password,
        inviteCode: registerForm.inviteCode
      }),
    })
    
    const data = await response.json()
    
    if (response.ok) {
      ElMessage.success('注册成功，请登录')
      showRegisterDialog.value = false
      handleDialogClose()
      // 自动填充用户名
      loginForm.username = registerForm.username
    } else {
      ElMessage.error(data.error || '注册失败')
    }
  } catch (error) {
    console.error('注册失败:', error)
    ElMessage.error('注册失败，请稍后重试')
  } finally {
    isRegistering.value = false
  }
}

// 关闭对话框时重置表单
const handleDialogClose = () => {
  if (registerFormRef.value) {
    registerFormRef.value.resetFields()
  }
  registerForm.username = ''
  registerForm.password = ''
  registerForm.confirmPassword = ''
  registerForm.inviteCode = ''
}

onMounted(() => {
  // 如果已经登录，直接跳转
  if (authStore.isAuthenticated) {
    router.push('/')
  }
  
  // 自动聚焦到用户名输入框
  const usernameInput = document.querySelector('input[placeholder="用户名"]') as HTMLInputElement
  if (usernameInput) {
    usernameInput.focus()
  }
})
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  background: white;
  border-radius: 16px;
  padding: 48px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 400px;
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-header h2 {
  color: #2c3e50;
  margin-bottom: 8px;
  font-weight: 600;
}

.login-header p {
  color: #64748b;
  margin: 0;
}

.login-form {
  margin-bottom: 24px;
}

.login-button {
  width: 100%;
  height: 48px;
  font-size: 16px;
  font-weight: 500;
}

.error-message {
  color: #ef4444;
  text-align: center;
  font-size: 14px;
  margin-top: 16px;
}

.register-link {
  text-align: center;
  margin-top: 16px;
}

.register-link .el-button {
  color: #667eea;
  font-size: 14px;
}

.register-link .el-button:hover {
  color: #764ba2;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
