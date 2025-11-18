<script setup lang="ts">
import { ref } from 'vue'
import { http } from '@/http'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'
import { handleApiResponse } from '@/utils/apiResponse'

const deleteAccountConfirm = ref(false)
const authStore = useAuthStore()
const router = useRouter()

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

</script>

<template>
  <el-form>
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