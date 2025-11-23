<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Edit, Search, Plus } from '@element-plus/icons-vue'
import { http } from '@/http'

interface VipState {
  userName: string
  vipLevel: string
  vipEndDate: string
}

interface UserOption {
  userName: string
}

const vipStates = ref<VipState[]>([])
const loading = ref(false)
const editDialogVisible = ref(false)
const addDialogVisible = ref(false)
const editingVipState = ref<VipState | null>(null)
const searchUserName = ref('')
const userOptions = ref<UserOption[]>([])
const userSearchLoading = ref(false)

const editForm = ref({
  vipLevel: '',
  vipEndDate: ''
})
const editFormRef = ref()

const addForm = ref({
  userName: '',
  vipLevel: '',
  vipEndDate: ''
})
const addFormRef = ref()

const vipLevelOptions = [
  { label: 'VIP Alpha', value: 'vip_alpha' },
  { label: 'VIP Omega', value: 'vip_omega' }
]

// 过滤后的VIP状态列表
const filteredVipStates = computed(() => {
  if (!searchUserName.value.trim()) {
    return vipStates.value
  }
  const searchTerm = searchUserName.value.trim().toLowerCase()
  return vipStates.value.filter(state => 
    state.userName.toLowerCase().includes(searchTerm)
  )
})

// 加载VIP状态列表
const loadVipStates = async () => {
  try {
    loading.value = true
    const response = await http.get('/vip')
    if (response.ok) {
      const data = await response.json()
      vipStates.value = data.data || []
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '加载VIP状态列表失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载VIP状态列表失败')
  } finally {
    loading.value = false
  }
}

// 打开编辑对话框
const handleEdit = (vipState: VipState) => {
  editingVipState.value = vipState
  editForm.value = {
    vipLevel: vipState.vipLevel || '',
    vipEndDate: vipState.vipEndDate || ''
  }
  editDialogVisible.value = true
}

// 保存编辑
const handleSave = async () => {
  if (!editFormRef.value || !editingVipState.value) return
  
  try {
    await editFormRef.value.validate()
    
    const response = await http.put(
      `/vip/${encodeURIComponent(editingVipState.value.userName)}`,
      {
        vipLevel: editForm.value.vipLevel || null,
        vipEndDate: editForm.value.vipEndDate || null
      }
    )
    
    if (response.ok) {
      ElMessage.success('更新成功')
      editDialogVisible.value = false
      loadVipStates()
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '更新失败')
    }
  } catch (error: any) {
    if (error?.message && !error.message.includes('validate')) {
      ElMessage.error(error.message || '更新失败')
    }
  }
}

// 格式化日期时间显示
const formatDateTime = (dateStr: string) => {
  if (!dateStr) return '-'
  try {
    return new Date(dateStr).toLocaleString('zh-CN')
  } catch {
    return dateStr
  }
}

// 判断VIP是否过期
const isExpired = (dateStr: string) => {
  if (!dateStr) return false
  try {
    return new Date(dateStr) < new Date()
  } catch {
    return false
  }
}

// 搜索用户（用于自动补全）
const searchUsers = async (queryString: string, callback: (results: UserOption[]) => void) => {
  if (!queryString || queryString.trim().length < 1) {
    callback([])
    return
  }
  
  try {
    userSearchLoading.value = true
    const response = await http.get(`/vip/search-users?query=${encodeURIComponent(queryString)}&limit=20`)
    if (response.ok) {
      const data = await response.json()
      const results = data.data || []
      callback(results)
    } else {
      callback([])
    }
  } catch (error: any) {
    // 静默失败，不影响用户体验
    callback([])
  } finally {
    userSearchLoading.value = false
  }
}

// 打开添加会员对话框
const handleAdd = () => {
  addForm.value = {
    userName: '',
    vipLevel: '',
    vipEndDate: ''
  }
  userOptions.value = []
  addDialogVisible.value = true
}

// 保存添加的会员
const handleAddSave = async () => {
  if (!addFormRef.value) return
  
  try {
    await addFormRef.value.validate()
    
    if (!addForm.value.userName || !addForm.value.userName.trim()) {
      ElMessage.error('请输入用户名')
      return
    }
    
    const response = await http.put(
      `/vip/${encodeURIComponent(addForm.value.userName.trim())}`,
      {
        vipLevel: addForm.value.vipLevel || null,
        vipEndDate: addForm.value.vipEndDate || null
      }
    )
    
    if (response.ok) {
      ElMessage.success('添加成功')
      addDialogVisible.value = false
      loadVipStates()
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '添加失败')
    }
  } catch (error: any) {
    if (error?.message && !error.message.includes('validate')) {
      ElMessage.error(error.message || '添加失败')
    }
  }
}

onMounted(() => {
  loadVipStates()
})
</script>

<template>
  <div class="vip-management">
    <div class="header">
      <h2>会员管理</h2>
      <el-button type="primary" @click="handleAdd">
        <el-icon><Plus /></el-icon>
        添加会员
      </el-button>
    </div>

    <div class="filter-section">
      <el-input
        v-model="searchUserName"
        placeholder="请输入用户名进行筛选"
        clearable
        style="width: 300px"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <el-table
      :data="filteredVipStates"
      v-loading="loading"
      stripe
      style="width: 100%"
    >
      <el-table-column prop="userName" label="用户名" width="200" />
      <el-table-column prop="vipLevel" label="VIP等级" width="150">
        <template #default="{ row }">
          <el-tag :type="row.vipLevel === 'vip_alpha' ? 'success' : 'warning'">
            {{ row.vipLevel === 'vip_alpha' ? 'VIP Alpha' : row.vipLevel === 'vip_omega' ? 'VIP Omega' : row.vipLevel || '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="vipEndDate" label="到期时间" width="200">
        <template #default="{ row }">
          <span :class="{ 'expired-text': isExpired(row.vipEndDate) }">
            {{ formatDateTime(row.vipEndDate) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="isExpired(row.vipEndDate) ? 'danger' : 'success'">
            {{ isExpired(row.vipEndDate) ? '已过期' : '有效' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            size="small"
            @click="handleEdit(row)"
          >
            <el-icon><Edit /></el-icon>
            编辑
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="editDialogVisible"
      :title="`编辑用户 ${editingVipState?.userName} 的VIP状态`"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="editFormRef"
        :model="editForm"
        label-width="100px"
      >
        <el-form-item
          label="VIP等级"
          prop="vipLevel"
          :rules="[
            { required: false, message: '请选择VIP等级', trigger: 'change' }
          ]"
        >
          <el-select
            v-model="editForm.vipLevel"
            placeholder="请选择VIP等级"
            style="width: 100%"
            clearable
          >
            <el-option
              v-for="option in vipLevelOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          label="到期时间"
          prop="vipEndDate"
          :rules="[
            { required: false, message: '请选择到期时间', trigger: 'change' }
          ]"
        >
          <el-date-picker
            v-model="editForm.vipEndDate"
            type="datetime"
            placeholder="请选择到期时间"
            style="width: 100%"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss"
            clearable
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 添加会员对话框 -->
    <el-dialog
      v-model="addDialogVisible"
      title="添加会员"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="addFormRef"
        :model="addForm"
        label-width="100px"
      >
        <el-form-item
          label="用户名"
          prop="userName"
          :rules="[
            { required: true, message: '请输入用户名', trigger: 'blur' }
          ]"
        >
          <el-autocomplete
            v-model="addForm.userName"
            :fetch-suggestions="searchUsers"
            placeholder="请输入用户名进行搜索"
            style="width: 100%"
            :loading="userSearchLoading"
            clearable
            value-key="userName"
            @select="(item: UserOption) => { addForm.userName = item.userName }"
          >
            <template #default="{ item }">
              <div>{{ item.userName }}</div>
            </template>
          </el-autocomplete>
        </el-form-item>
        <el-form-item
          label="VIP等级"
          prop="vipLevel"
          :rules="[
            { required: false, message: '请选择VIP等级', trigger: 'change' }
          ]"
        >
          <el-select
            v-model="addForm.vipLevel"
            placeholder="请选择VIP等级"
            style="width: 100%"
            clearable
          >
            <el-option
              v-for="option in vipLevelOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          label="到期时间"
          prop="vipEndDate"
          :rules="[
            { required: false, message: '请选择到期时间', trigger: 'change' }
          ]"
        >
          <el-date-picker
            v-model="addForm.vipEndDate"
            type="datetime"
            placeholder="请选择到期时间"
            style="width: 100%"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss"
            clearable
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAddSave">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.vip-management {
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

.expired-text {
  color: #f56c6c;
}
</style>

