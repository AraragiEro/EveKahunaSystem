<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h2>登录 Kahuna System</h2>
        <p>请输入账号信息继续使用</p>
      </div>

      <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" class="login-form">
        <el-form-item prop="username">
          <el-input
            ref="usernameInputRef"
            v-model="loginForm.username"
            placeholder="用户名"
            size="large"
            :prefix-icon="User"
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
            :prefix-icon="Lock"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" class="login-button" :loading="authStore.isLoading" @click="handleLogin">
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="register-link">
        <el-button type="text" size="default" @click="showRegisterDialog = true">还没有账号？立即注册</el-button>
      </div>

      <div v-if="authStore.error" class="error-message">
        {{ authStore.error }}
      </div>
    </div>

    <el-dialog v-model="showRegisterDialog" title="注册账号" width="420px" :close-on-click-modal="false" @close="handleDialogClose">
      <el-form ref="registerFormRef" :model="registerForm" :rules="registerRules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="registerForm.username" placeholder="仅支持英文字母和数字" size="large" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input v-model="registerForm.password" type="password" placeholder="至少 6 位" size="large" show-password />
        </el-form-item>

        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input v-model="registerForm.confirmPassword" type="password" placeholder="再次输入密码" size="large" show-password />
        </el-form-item>

        <el-form-item label="邀请码" prop="inviteCode">
          <el-input v-model="registerForm.inviteCode" placeholder="请输入邀请码" size="large" />
        </el-form-item>

        <div class="register-tip" v-if="showQQGroupButton">邀请码获取请加入 QQ 交流群：{{ QQGroupNumber }}</div>
      </el-form>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="showRegisterDialog = false">取消</el-button>
          <el-button type="primary" :loading="isRegistering" @click="handleRegister">确认</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()
const usernameInputRef = ref<any>()
const passwordInputRef = ref<any>()

const showRegisterDialog = ref(false)
const isRegistering = ref(false)
const QQGroupNumber = computed(() => import.meta.env.VITE_QQ_GROUP as string | undefined)
const showQQGroupButton = computed(() => !!QQGroupNumber.value)

const loginForm = reactive({
  username: '',
  password: '',
})

const registerForm = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  inviteCode: '',
})

const validateUsername = (_rule: unknown, value: string, callback: (err?: Error) => void) => {
  if (!value) return callback(new Error('请输入用户名'))
  if (!/^[a-zA-Z0-9]+$/.test(value)) return callback(new Error('用户名只能包含英文字母和数字'))
  callback()
}

const validateConfirmPassword = (_rule: unknown, value: string, callback: (err?: Error) => void) => {
  if (!value) return callback(new Error('请再次输入密码'))
  if (value !== registerForm.password) return callback(new Error('两次输入的密码不一致'))
  callback()
}

const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const registerRules: FormRules = {
  username: [{ required: true, validator: validateUsername, trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度至少 6 位', trigger: 'blur' },
  ],
  confirmPassword: [{ required: true, validator: validateConfirmPassword, trigger: 'blur' }],
  inviteCode: [{ required: true, message: '请输入邀请码', trigger: 'blur' }],
}

const focusPassword = () => {
  passwordInputRef.value?.focus?.()
}

const handleLogin = async () => {
  if (!loginFormRef.value) return
  try {
    await loginFormRef.value.validate()
    const result = await authStore.login(loginForm)
    if (!result.success) {
      ElMessage.error(result.error || '登录失败')
      return
    }

    ElMessage.success('登录成功')
    await nextTick()
    if (authStore.user?.roles.includes('vip_alpha') || authStore.user?.roles.includes('vip_omega')) {
      router.push('/home')
    } else {
      router.push('/todolist')
    }
  } catch (error) {
    console.error('登录失败:', error)
  }
}

const handleRegister = async () => {
  if (!registerFormRef.value) return

  try {
    await registerFormRef.value.validate()
    isRegistering.value = true
    const response = await fetch('/api/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: registerForm.username,
        password: registerForm.password,
        inviteCode: registerForm.inviteCode,
      }),
    })
    const data = await response.json()

    if (data.status === 200) {
      ElMessage.success(data.message || '注册成功，请登录')
      showRegisterDialog.value = false
      handleDialogClose()
      loginForm.username = registerForm.username
      return
    }
    ElMessage.error(data.message || '注册失败')
  } catch (error) {
    console.error('注册失败:', error)
    ElMessage.error('注册失败，请稍后重试')
  } finally {
    isRegistering.value = false
  }
}

const handleDialogClose = () => {
  registerFormRef.value?.resetFields()
  registerForm.username = ''
  registerForm.password = ''
  registerForm.confirmPassword = ''
  registerForm.inviteCode = ''
}

onMounted(async () => {
  if (authStore.token) {
    const isAuthValid = await authStore.checkAuth()
    if (isAuthValid) {
      router.push('/home')
      return
    }
  }
  usernameInputRef.value?.focus?.()
})
</script>

<style scoped>
.login-container {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--k-hero-bg);
  padding: 20px;
}

.login-card {
  width: 100%;
  max-width: 420px;
  border-radius: 16px;
  border: 1px solid color-mix(in srgb, var(--k-color-primary) 24%, var(--k-color-border));
  padding: 34px 28px;
  background: color-mix(in srgb, var(--k-color-surface) 92%, transparent);
  box-shadow: var(--k-shadow-md);
}

.login-header {
  text-align: center;
  margin-bottom: 24px;
}

.login-header h2 {
  margin: 0 0 8px;
  color: var(--k-color-text);
}

.login-header p {
  margin: 0;
  color: var(--k-color-text-secondary);
}

.login-form {
  margin-bottom: 12px;
}

.login-button {
  width: 100%;
  height: 46px;
  border-radius: 10px;
}

.error-message {
  margin-top: 10px;
  text-align: center;
  color: var(--k-color-danger);
}

.register-link,
.register-tip {
  text-align: center;
}

.register-link :deep(.el-button) {
  color: var(--k-color-primary);
}

.register-tip {
  margin-top: 8px;
  color: var(--k-color-text-secondary);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
