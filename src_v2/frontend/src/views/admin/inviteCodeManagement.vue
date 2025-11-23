<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, DocumentCopy } from '@element-plus/icons-vue'
import { http } from '@/http'

interface InviteCode {
  inviteCode: string
  creatorUserName: string
  createDate: string
  usedCountCurrent: number
  usedCountMax: number
  remainingCount: number
}

interface InviteCodeUser {
  userName: string
  usedDate: string
}

const inviteCodes = ref<InviteCode[]>([])
const loading = ref(false)
const onlyAvailable = ref(false)
const generateDialogVisible = ref(false)
const usersDialogVisible = ref(false)
const selectedInviteCode = ref<string>('')
const inviteCodeUsers = ref<InviteCodeUser[]>([])

const generateForm = ref({
  usedCountMax: 1
})
const generateFormRef = ref()

// 加载邀请码列表
const loadInviteCodes = async () => {
  try {
    loading.value = true
    const params = onlyAvailable.value ? '?onlyAvailable=true' : ''
    const response = await http.get(`/invite-code${params}`)
    if (response.ok) {
      const data = await response.json()
      inviteCodes.value = data.data || []
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '加载邀请码列表失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载邀请码列表失败')
  } finally {
    loading.value = false
  }
}

// 生成邀请码
const handleGenerate = async () => {
  if (!generateFormRef.value) return
  
  try {
    await generateFormRef.value.validate()
    const response = await http.post('/invite-code', {
      usedCountMax: generateForm.value.usedCountMax
    })
    
    if (response.ok) {
      const data = await response.json()
      ElMessage.success(`邀请码生成成功: ${data.data.inviteCode}`)
      generateDialogVisible.value = false
      generateForm.value = { usedCountMax: 1 }
      loadInviteCodes()
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '生成邀请码失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '生成邀请码失败')
  }
}

// 查看使用用户
const handleViewUsers = async (inviteCode: string) => {
  try {
    selectedInviteCode.value = inviteCode
    const response = await http.get(`/invite-code/${encodeURIComponent(inviteCode)}/users`)
    if (response.ok) {
      const data = await response.json()
      inviteCodeUsers.value = data.data || []
      usersDialogVisible.value = true
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '获取用户列表失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '获取用户列表失败')
  }
}

// 复制邀请码
const handleCopyCode = async (code: string) => {
  try {
    await navigator.clipboard.writeText(code)
    ElMessage.success('邀请码已复制到剪贴板')
  } catch (error) {
    ElMessage.error('复制失败')
  }
}

// 筛选切换
const handleFilterChange = () => {
  loadInviteCodes()
}

onMounted(() => {
  loadInviteCodes()
})
</script>

<template>
  <div class="invite-code-management">
    <div class="header">
      <h2>邀请码管理</h2>
      <el-button type="primary" @click="generateDialogVisible = true">
        <el-icon><Plus /></el-icon>
        生成邀请码
      </el-button>
    </div>

    <div class="filter-section">
      <el-checkbox v-model="onlyAvailable" @change="handleFilterChange">
        只显示未使用完的邀请码
      </el-checkbox>
    </div>

    <el-table
      :data="inviteCodes"
      v-loading="loading"
      stripe
      style="width: 100%"
    >
      <el-table-column prop="inviteCode" label="邀请码" width="350">
        <template #default="{ row }">
          <div class="code-cell">
            <span class="code-text">{{ row.inviteCode }}</span>
            <el-button
              link
              type="primary"
              size="small"
              @click="handleCopyCode(row.inviteCode)"
            >
              <el-icon><DocumentCopy /></el-icon>
            </el-button>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="creatorUserName" label="创建者" width="120" />
      <el-table-column prop="createDate" label="创建时间" width="180">
        <template #default="{ row }">
          {{ new Date(row.createDate).toLocaleString('zh-CN') }}
        </template>
      </el-table-column>
      <el-table-column label="使用情况" width="150">
        <template #default="{ row }">
          <span :class="{ 'text-warning': row.remainingCount === 0 }">
            {{ row.usedCountCurrent }} / {{ row.usedCountMax }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="remainingCount" label="剩余次数" width="100">
        <template #default="{ row }">
          <el-tag :type="row.remainingCount > 0 ? 'success' : 'danger'">
            {{ row.remainingCount }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.remainingCount > 0 ? 'success' : 'info'">
            {{ row.remainingCount > 0 ? '可用' : '已用完' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            size="small"
            @click="handleViewUsers(row.inviteCode)"
          >
            查看用户
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 生成邀请码对话框 -->
    <el-dialog
      v-model="generateDialogVisible"
      title="生成邀请码"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="generateFormRef"
        :model="generateForm"
        label-width="120px"
      >
        <el-form-item
          label="使用次数上限"
          prop="usedCountMax"
          :rules="[
            { required: true, message: '请输入使用次数上限', trigger: 'blur' },
            { type: 'number', min: 1, message: '使用次数上限必须大于0', trigger: 'blur' }
          ]"
        >
          <el-input-number
            v-model="generateForm.usedCountMax"
            :min="1"
            :max="1000"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="generateDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleGenerate">生成</el-button>
      </template>
    </el-dialog>

    <!-- 查看用户对话框 -->
    <el-dialog
      v-model="usersDialogVisible"
      :title="`邀请码 ${selectedInviteCode} 的使用用户`"
      width="600px"
    >
      <el-table :data="inviteCodeUsers" stripe>
        <el-table-column prop="userName" label="用户名" width="200" />
        <el-table-column prop="usedDate" label="使用时间" width="300">
          <template #default="{ row }">
            {{ new Date(row.usedDate).toLocaleString('zh-CN') }}
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="usersDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.invite-code-management {
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h2 {
  margin: 0;
}

.filter-section {
  margin-bottom: 20px;
}

.code-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.code-text {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  word-break: break-all;
  flex: 1;
}

.text-warning {
  color: #e6a23c;
}
</style>

