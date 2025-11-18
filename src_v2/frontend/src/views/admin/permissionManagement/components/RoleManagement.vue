<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { http } from '@/http'
import type { Role } from '../types'
import RoleHierarchyDialog from './RoleHierarchyDialog.vue'
import RolePermissionDialog from './RolePermissionDialog.vue'

const roles = ref<Role[]>([])
const roleDialogVisible = ref(false)
const roleForm = ref({
  roleName: '',
  roleDescription: ''
})
const roleFormRef = ref()

const hierarchyDialogVisible = ref(false)
const selectedRoleForHierarchy = ref<Role | null>(null)

const rolePermissionDialogVisible = ref(false)
const selectedRoleForPermission = ref<Role | null>(null)

// 加载角色列表
const loadRoles = async () => {
  try {
    const response = await http.get('/permission/roles')
    if (response.ok) {
      const data = await response.json()
      roles.value = data.data || []
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '加载角色列表失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载角色列表失败')
  }
}

// 创建角色
const handleCreateRole = async () => {
  if (!roleFormRef.value) return
  
  try {
    await roleFormRef.value.validate()
    const response = await http.post('/permission/roles', {
      roleName: roleForm.value.roleName,
      roleDescription: roleForm.value.roleDescription
    })
    
    if (response.ok) {
      ElMessage.success('角色创建成功')
      roleDialogVisible.value = false
      roleForm.value = { roleName: '', roleDescription: '' }
      loadRoles()
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '创建角色失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '创建角色失败')
  }
}

// 删除角色
const handleDeleteRole = async (role: Role) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除角色 "${role.roleName}" 吗？`,
      '删除角色',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    // 询问是否包含子角色
    let includeChildren = false
    try {
      await ElMessageBox.confirm(
        '是否同时删除该角色的所有子角色？',
        '删除确认',
        {
          confirmButtonText: '是',
          cancelButtonText: '否',
          type: 'warning'
        }
      )
      includeChildren = true
    } catch {
      includeChildren = false
    }
    
    const response = await http.delete('/permission/roles', {
      roleName: role.roleName,
      includeChildren
    })
    
    if (response.ok) {
      ElMessage.success('角色删除成功')
      loadRoles()
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '删除角色失败')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error?.message || '删除角色失败')
    }
  }
}

// 打开层级关系对话框
const openHierarchyDialog = (role: Role) => {
  selectedRoleForHierarchy.value = role
  hierarchyDialogVisible.value = true
}

// 打开权限管理对话框
const openRolePermissionDialog = (role: Role) => {
  selectedRoleForPermission.value = role
  rolePermissionDialogVisible.value = true
}

// 刷新角色列表
const refreshRoles = () => {
  loadRoles()
}

onMounted(() => {
  loadRoles()
})

defineExpose({
  refreshRoles
})
</script>

<template>
  <div class="role-management">
    <div class="toolbar">
      <el-button type="primary" @click="roleDialogVisible = true">创建角色</el-button>
    </div>
    <el-table :data="roles" border stripe style="width: 100%">
      <el-table-column prop="roleName" label="角色名称" width="200" />
      <el-table-column prop="roleDescription" label="角色描述" />
      <el-table-column label="操作" width="400" fixed="right">
        <template #default="scope">
          <el-button size="small" @click="openHierarchyDialog(scope.row)">管理层级关系</el-button>
          <el-button size="small" type="primary" @click="openRolePermissionDialog(scope.row)">管理权限</el-button>
          <el-button size="small" type="danger" @click="handleDeleteRole(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建角色对话框 -->
    <el-dialog v-model="roleDialogVisible" title="创建角色" width="500px">
      <el-form ref="roleFormRef" :model="roleForm" label-width="100px">
        <el-form-item label="角色名称" prop="roleName" :rules="[{ required: true, message: '请输入角色名称', trigger: 'blur' }]">
          <el-input v-model="roleForm.roleName" placeholder="请输入角色名称" />
        </el-form-item>
        <el-form-item label="角色描述" prop="roleDescription">
          <el-input v-model="roleForm.roleDescription" type="textarea" placeholder="请输入角色描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="roleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateRole">确定</el-button>
      </template>
    </el-dialog>

    <!-- 角色层级关系对话框 -->
    <RoleHierarchyDialog
      v-model="hierarchyDialogVisible"
      :role="selectedRoleForHierarchy"
      @refresh="refreshRoles"
    />

    <!-- 角色权限关联对话框 -->
    <RolePermissionDialog
      v-model="rolePermissionDialogVisible"
      :role="selectedRoleForPermission"
    />
  </div>
</template>

<style scoped>
.role-management {
  padding: 20px;
}

.toolbar {
  margin-bottom: 20px;
}
</style>

