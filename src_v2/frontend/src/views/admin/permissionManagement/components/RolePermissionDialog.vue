<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { http } from '@/http'
import type { Role, Permission } from '../types'

interface Props {
  modelValue: boolean
  role: Role | null
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const dialogVisible = ref(false)
const rolePermissions = ref<string[]>([])
const rolePermissionForm = ref({
  selectedPermissionsToAdd: [] as string[],
  selectedPermissionsToRemove: [] as string[]
})
const permissions = ref<Permission[]>([])

watch(() => props.modelValue, (val) => {
  dialogVisible.value = val
  if (val && props.role) {
    loadRolePermissions()
    loadPermissions()
  }
})

watch(dialogVisible, (val) => {
  emit('update:modelValue', val)
})

const loadRolePermissions = async () => {
  if (!props.role) return
  
  try {
    const response = await http.get(`/permission/roles/${props.role.roleName}/permissions`)
    if (response.ok) {
      const data = await response.json()
      rolePermissions.value = data.data || []
      rolePermissionForm.value = {
        selectedPermissionsToAdd: [],
        selectedPermissionsToRemove: []
      }
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '加载角色权限失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载角色权限失败')
  }
}

const loadPermissions = async () => {
  try {
    const response = await http.get('/permission/permissions')
    if (response.ok) {
      const data = await response.json()
      permissions.value = data.data || []
    }
  } catch (error: any) {
    // 静默失败
  }
}

// 批量添加权限
const handleAddPermissionsToRole = async () => {
  if (!props.role || rolePermissionForm.value.selectedPermissionsToAdd.length === 0) return
  
  try {
    const promises = rolePermissionForm.value.selectedPermissionsToAdd.map(permissionName =>
      http.post('/permission/roles/permissions', {
        roleName: props.role!.roleName,
        permissionName: permissionName
      })
    )
    
    await Promise.all(promises)
    ElMessage.success(`成功添加 ${rolePermissionForm.value.selectedPermissionsToAdd.length} 个权限`)
    rolePermissionForm.value.selectedPermissionsToAdd = []
    loadRolePermissions()
  } catch (error: any) {
    ElMessage.error(error?.message || '添加角色权限失败')
  }
}

// 移除角色的权限
const handleRemovePermissionFromRole = async (permissionName: string) => {
  if (!props.role) return
  
  try {
    await ElMessageBox.confirm(
      `确定要从角色 "${props.role.roleName}" 移除权限 "${permissionName}" 吗？`,
      '移除权限',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const response = await http.delete('/permission/roles/permissions', {
      roleName: props.role.roleName,
      permissionName: permissionName
    })
    
    if (response.ok) {
      ElMessage.success('角色权限移除成功')
      loadRolePermissions()
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '移除角色权限失败')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error?.message || '移除角色权限失败')
    }
  }
}

// 批量移除权限
const handleBatchRemovePermissions = async () => {
  if (!props.role || rolePermissionForm.value.selectedPermissionsToRemove.length === 0) return
  
  try {
    await ElMessageBox.confirm(
      `确定要从角色 "${props.role.roleName}" 移除 ${rolePermissionForm.value.selectedPermissionsToRemove.length} 个权限吗？`,
      '批量移除权限',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const promises = rolePermissionForm.value.selectedPermissionsToRemove.map(permissionName =>
      http.delete('/permission/roles/permissions', {
        roleName: props.role!.roleName,
        permissionName: permissionName
      })
    )
    
    await Promise.all(promises)
    ElMessage.success(`成功移除 ${rolePermissionForm.value.selectedPermissionsToRemove.length} 个权限`)
    rolePermissionForm.value.selectedPermissionsToRemove = []
    loadRolePermissions()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error?.message || '批量移除权限失败')
    }
  }
}
</script>

<template>
  <el-dialog v-model="dialogVisible" :title="`管理角色权限 - ${role?.roleName}`" width="800px">
    <div class="role-permission-content">
      <!-- 当前角色信息 -->
      <div class="current-role-info">
        <el-card shadow="never" class="role-card">
          <template #header>
            <div class="card-header">
              <span class="role-name">{{ role?.roleName }}</span>
              <el-tag type="info" size="small">当前角色</el-tag>
            </div>
          </template>
          <div class="role-description">
            {{ role?.roleDescription || '暂无描述' }}
          </div>
        </el-card>
      </div>

      <!-- 角色权限区域 -->
      <el-card shadow="never" class="permissions-card">
        <template #header>
          <div class="card-header">
            <span>当前权限 ({{ rolePermissions.length }})</span>
          </div>
        </template>
        <div class="permissions-tags">
          <el-tag
            v-for="permission in rolePermissions"
            :key="permission"
            closable
            @close="handleRemovePermissionFromRole(permission)"
            type="success"
            size="large"
            class="permission-tag"
          >
            {{ permission }}
          </el-tag>
          <div v-if="rolePermissions.length === 0" class="empty-text">暂无权限</div>
        </div>
        <el-divider />
        <div class="add-permissions-section">
          <div class="section-title">添加权限</div>
          <el-select
            v-model="rolePermissionForm.selectedPermissionsToAdd"
            placeholder="选择多个权限（支持多选）"
            filterable
            multiple
            style="width: 100%"
            collapse-tags
            collapse-tags-tooltip
          >
            <el-option
              v-for="permission in permissions.filter(p => !rolePermissions.includes(p.permissionName))"
              :key="permission.permissionName"
              :label="permission.permissionName"
              :value="permission.permissionName"
            >
              <span>{{ permission.permissionName }}</span>
              <span v-if="permission.permissionDescription" class="permission-description-text"> - {{ permission.permissionDescription }}</span>
            </el-option>
          </el-select>
          <el-button
            type="primary"
            :disabled="rolePermissionForm.selectedPermissionsToAdd.length === 0"
            @click="handleAddPermissionsToRole"
            style="margin-top: 10px; width: 100%"
          >
            批量添加权限 ({{ rolePermissionForm.selectedPermissionsToAdd.length }})
          </el-button>
        </div>
        <el-divider v-if="rolePermissions.length > 0" />
        <div v-if="rolePermissions.length > 0" class="remove-permissions-section">
          <div class="section-title">移除权限</div>
          <el-select
            v-model="rolePermissionForm.selectedPermissionsToRemove"
            placeholder="选择要移除的权限（支持多选）"
            filterable
            multiple
            style="width: 100%"
            collapse-tags
            collapse-tags-tooltip
          >
            <el-option
              v-for="permission in rolePermissions"
              :key="permission"
              :label="permission"
              :value="permission"
            />
          </el-select>
          <el-button
            type="danger"
            :disabled="rolePermissionForm.selectedPermissionsToRemove.length === 0"
            @click="handleBatchRemovePermissions"
            style="margin-top: 10px; width: 100%"
          >
            批量移除权限 ({{ rolePermissionForm.selectedPermissionsToRemove.length }})
          </el-button>
        </div>
      </el-card>
    </div>
    <template #footer>
      <el-button @click="dialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.role-permission-content {
  max-height: 600px;
  overflow-y: auto;
}

.current-role-info {
  margin-bottom: 20px;
}

.role-card {
  border: 2px solid #409eff;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.role-name {
  font-weight: bold;
  font-size: 16px;
}

.role-description {
  color: #666;
  font-size: 14px;
}

.permissions-card {
  margin-bottom: 20px;
}

.permissions-tags {
  min-height: 60px;
  padding: 10px 0;
}

.permission-tag {
  margin-right: 8px;
  margin-bottom: 8px;
  font-size: 14px;
  padding: 0 12px;
  height: 32px;
  line-height: 32px;
}

.add-permissions-section,
.remove-permissions-section {
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

.permission-description-text {
  color: #999;
  font-size: 12px;
}
</style>

