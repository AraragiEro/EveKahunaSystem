<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { http } from '@/http'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'
import { handleApiResponse } from '@/utils/apiResponse'

const deleteAccountConfirm = ref(false)
const authStore = useAuthStore()
const router = useRouter()
const boundQQ = ref('')
const bindCommandLoading = ref(false)
const unbindLoading = ref(false)

const fetchQQBinding = async () => {
  try {
    const response = await http.get('/user/qqBinding')
    const data = await handleApiResponse(response, '获取QQ绑定失败')
    if (data) {
      boundQQ.value = data?.userQQ ? String(data.userQQ) : ''
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '获取QQ绑定失败')
  }
}

const copyTextToClipboard = async (text: string) => {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch (error) {
    console.warn('clipboard api failed:', error)
  }

  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.focus()
    textarea.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(textarea)
    return ok
  } catch (error) {
    console.warn('fallback copy failed:', error)
    return false
  }
}

const handleCopyBindingCommand = async () => {
  if (bindCommandLoading.value) {
    return
  }
  bindCommandLoading.value = true
  try {
    const response = await http.post('/user/qqBinding/create')
    const data = await handleApiResponse(response, '生成绑定指令失败')
    if (!data) {
      return
    }
    const instruction = data?.instruction || `.绑定kahunasystem ${data?.uuid || ''}`.trim()
    const copied = await copyTextToClipboard(instruction)
    if (copied) {
      ElMessage.success('已复制绑定指令，请在5分钟内发送给机器人')
    } else {
      ElMessage.error('复制失败，请手动复制绑定指令')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '生成绑定指令失败')
  } finally {
    bindCommandLoading.value = false
  }
}

const handleUnbindQQ = async () => {
  if (!boundQQ.value || unbindLoading.value) {
    return
  }
  unbindLoading.value = true
  try {
    const response = await http.post('/user/qqBinding/unbind')
    const data = await handleApiResponse(response, '解绑失败')
    if (data) {
      ElMessage.success(data.message || '解绑成功')
      boundQQ.value = ''
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '解绑失败')
  } finally {
    unbindLoading.value = false
  }
}

const handleDeleteAccount = async () => {
  try {
    const response = await http.post('/auth/deleteAccount')
    const data = await handleApiResponse(response, '注销失败')
    if (data) {
      ElMessage.success(data.message || '注销成功')
      authStore.logout()
      router.push('/login')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '注销失败')
  }
}

onMounted(() => {
  fetchQQBinding()
})

</script>

<template>
  <el-form>
    <el-form-item label="绑定QQ">
      <template #label>
        <span class="form-item-label">绑定QQ</span>
      </template>
      <el-input v-model="boundQQ" placeholder="未绑定" disabled />
    </el-form-item>
    <el-form-item label="绑定操作">
      <template #label>
        <span class="form-item-label">绑定操作</span>
      </template>
      <el-button type="primary" :loading="bindCommandLoading" @click="handleCopyBindingCommand">复制绑定指令</el-button>
      <el-button type="warning" :loading="unbindLoading" :disabled="!boundQQ" @click="handleUnbindQQ">解绑</el-button>
    </el-form-item>
    <el-form-item label="注销账号">
      <template #label>
        <span class="form-item-label">注销账号</span>
      </template>
      <el-button type="danger" @click="deleteAccountConfirm = true">注销</el-button>
    </el-form-item>
  </el-form>

  <el-dialog v-model="deleteAccountConfirm" title="注销账号" width="30%" center>
    <span>请知悉</span><br>
    <span>注销账号后，一下信息将永久从网站删除</span><br>
    <span>1. 账号信息</span><br>
    <span>2. 所有绑定角色的esi信息</span><br></br>
    <span>3. 所有使用绑定角色esi获取的数据</span><br></br>
    <span>3. 所有工业配置</span><br></br>
    <template #footer>
      <el-button type="primary" @click="handleDeleteAccount">注销</el-button>
    </template>
  </el-dialog>
</template>


<style scoped>
.form-item-label {
  font-weight: bold;
  font-size: 16px;
}

</style>
