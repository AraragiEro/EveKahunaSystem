<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { http } from '@/http'
import type { User, Role } from '../types'

const users = ref<User[]>([])
const userRoleDialogVisible = ref(false)
const selectedUserForRole = ref<User | null>(null)
const userRoles = ref<string[]>([])
const userRoleForm = ref({
  selectedRolesToAdd: [] as string[],
  selectedRolesToRemove: [] as string[]
})
const roles = ref<Role[]>([])

// 加载用户列表
const loadUsers = async () => {
  try {
    const response = await http.get('/permission/users')
    if (response.ok) {
      const data = await response.json()
      users.value = data.data || []
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '加载用户列表失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载用户列表失败')
  }
}

// 加载角色列表
const loadRoles = async () => {
  try {
    const response = await http.get('/permission/roles')
    if (response.ok) {
      const data = await response.json()
      roles.value = data.data || []
    }
  } catch (error: any) {
    // 静默失败
  }
}

// 打开用户角色关联对话框
const openUserRoleDialog = async (user: User) => {
  selectedUserForRole.value = user
  userRoleDialogVisible.value = true
  
  try {
    const response = await http.get(`/permission/users/${user.userName}/roles`)
    if (response.ok) {
      const data = await response.json()
      userRoles.value = data.data || []
      userRoleForm.value = {
        selectedRolesToAdd: [],
        selectedRolesToRemove: []
      }
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '加载用户角色失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载用户角色失败')
  }
}

// 批量添加角色
const handleAddRolesToUser = async () => {
  if (!selectedUserForRole.value || userRoleForm.value.selectedRolesToAdd.length === 0) return
  
  try {
    const promises = userRoleForm.value.selectedRolesToAdd.map(roleName =>
      http.post('/permission/users/roles', {
        userName: selectedUserForRole.value!.userName,
        roleName: roleName
      })
    )
    
    await Promise.all(promises)
    ElMessage.success(`成功添加 ${userRoleForm.value.selectedRolesToAdd.length} 个角色`)
    userRoleForm.value.selectedRolesToAdd = []
    if (selectedUserForRole.value) {
      openUserRoleDialog(selectedUserForRole.value)
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '添加用户角色失败')
  }
}

// 移除用户的角色
const handleRemoveRoleFromUser = async (roleName: string) => {
  if (!selectedUserForRole.value) return
  
  try {
    await ElMessageBox.confirm(
      `确定要从用户 "${selectedUserForRole.value.userName}" 移除角色 "${roleName}" 吗？`,
      '移除角色',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const response = await http.delete('/permission/users/roles', {
      userName: selectedUserForRole.value.userName,
      roleName: roleName
    })
    
    if (response.ok) {
      ElMessage.success('用户角色移除成功')
      if (selectedUserForRole.value) {
        openUserRoleDialog(selectedUserForRole.value)
      }
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '移除用户角色失败')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error?.message || '移除用户角色失败')
    }
  }
}

// 批量移除角色
const handleBatchRemoveRoles = async () => {
  if (!selectedUserForRole.value || userRoleForm.value.selectedRolesToRemove.length === 0) return
  
  try {
    await ElMessageBox.confirm(
      `确定要从用户 "${selectedUserForRole.value.userName}" 移除 ${userRoleForm.value.selectedRolesToRemove.length} 个角色吗？`,
      '批量移除角色',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const promises = userRoleForm.value.selectedRolesToRemove.map(roleName =>
      http.delete('/permission/users/roles', {
        userName: selectedUserForRole.value!.userName,
        roleName: roleName
      })
    )
    
    await Promise.all(promises)
    ElMessage.success(`成功移除 ${userRoleForm.value.selectedRolesToRemove.length} 个角色`)
    userRoleForm.value.selectedRolesToRemove = []
    if (selectedUserForRole.value) {
      openUserRoleDialog(selectedUserForRole.value)
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error?.message || '批量移除角色失败')
    }
  }
}

onMounted(() => {
  loadUsers()
  loadRoles()
})
</script>

<template>
  <div class="user-role-management">
    <el-table :data="users" border stripe style="width: 100%">
      <el-table-column prop="userName" label="用户名" width="200" />
      <el-table-column prop="createDate" label="创建时间" width="200" />
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="scope">
          <el-button size="small" type="primary" @click="openUserRoleDialog(scope.row)">管理角色</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 用户角色关联对话框 -->
    <el-dialog v-model="userRoleDialogVisible" :title="`管理用户角色 - ${selectedUserForRole?.userName}`" width="800px">
      <div class="user-role-content">
        <!-- 当前用户信息 -->
        <div class="current-user-info">
          <el-card shadow="never" class="user-card">
            <template #header>
              <div class="card-header">
                <span class="user-name">{{ selectedUserForRole?.userName }}</span>
                <el-tag type="info" size="small">当前用户</el-tag>
              </div>
            </template>
            <div class="user-info">
              <div class="info-item">
                <span class="info-label">创建时间：</span>
                <span class="info-value">{{ selectedUserForRole?.createDate || '未知' }}</span>
              </div>
            </div>
          </el-card>
        </div>

        <!-- 用户角色区域 -->
        <el-card shadow="never" class="roles-card">
          <template #header>
            <div class="card-header">
              <span>当前角色 ({{ userRoles.length }})</span>
            </div>
          </template>
          <div class="roles-tags">
            <el-tag
              v-for="role in userRoles"
              :key="role"
              closable
              @close="handleRemoveRoleFromUser(role)"
              type="primary"
              size="large"
              class="role-tag"
            >
              {{ role }}
            </el-tag>
            <div v-if="userRoles.length === 0" class="empty-text">暂无角色</div>
          </div>
          <el-divider />
          <div class="add-roles-section">
            <div class="section-title">添加角色</div>
            <el-select
              v-model="userRoleForm.selectedRolesToAdd"
              placeholder="选择多个角色（支持多选）"
              filterable
              multiple
              style="width: 100%"
              collapse-tags
              collapse-tags-tooltip
            >
              <el-option
                v-for="role in roles.filter(r => !userRoles.includes(r.roleName))"
                :key="role.roleName"
                :label="role.roleName"
                :value="role.roleName"
              >
                <span>{{ role.roleName }}</span>
                <span v-if="role.roleDescription" class="role-description-text"> - {{ role.roleDescription }}</span>
              </el-option>
            </el-select>
            <el-button
              type="primary"
              :disabled="userRoleForm.selectedRolesToAdd.length === 0"
              @click="handleAddRolesToUser"
              style="margin-top: 10px; width: 100%"
            >
              批量添加角色 ({{ userRoleForm.selectedRolesToAdd.length }})
            </el-button>
          </div>
          <el-divider v-if="userRoles.length > 0" />
          <div v-if="userRoles.length > 0" class="remove-roles-section">
            <div class="section-title">移除角色</div>
            <el-select
              v-model="userRoleForm.selectedRolesToRemove"
              placeholder="选择要移除的角色（支持多选）"
              filterable
              multiple
              style="width: 100%"
              collapse-tags
              collapse-tags-tooltip
            >
              <el-option
                v-for="role in userRoles"
                :key="role"
                :label="role"
                :value="role"
              />
            </el-select>
            <el-button
              type="danger"
              :disabled="userRoleForm.selectedRolesToRemove.length === 0"
              @click="handleBatchRemoveRoles"
              style="margin-top: 10px; width: 100%"
            >
              批量移除角色 ({{ userRoleForm.selectedRolesToRemove.length }})
            </el-button>
          </div>
        </el-card>
      </div>
      <template #footer>
        <el-button @click="userRoleDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.user-role-management {
  padding: 20px;
}

.user-role-content {
  max-height: 600px;
  overflow-y: auto;
}

.current-user-info {
  margin-bottom: 20px;
}

.user-card {
  border: 2px solid #409eff;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.user-name {
  font-weight: bold;
  font-size: 16px;
}

.user-info {
  color: #666;
  font-size: 14px;
}

.info-item {
  margin-bottom: 8px;
}

.info-label {
  font-weight: 500;
  color: #333;
}

.info-value {
  color: #666;
}

.roles-card {
  margin-bottom: 20px;
}

.roles-tags {
  min-height: 60px;
  padding: 10px 0;
}

.role-tag {
  margin-right: 8px;
  margin-bottom: 8px;
  font-size: 14px;
  padding: 0 12px;
  height: 32px;
  line-height: 32px;
}

.add-roles-section,
.remove-roles-section {
  padding-top: 10px;
}

.section-title {
  font-size: 14px;
  font-weight: bold;
  margin-bottom: 10px;
  color: #333;
}

.empty-text {
  color: #999;
  font-size: 14px;
  padding: 10px 0;
}

.role-description-text {
  color: #999;
  font-size: 12px;
}
</style>

