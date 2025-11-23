<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { http } from '@/http'
import type { Permission } from '../types'

const permissions = ref<Permission[]>([])
const permissionDialogVisible = ref(false)
const permissionForm = ref({
  permissionName: '',
  operation: '',
  permissionDescription: ''
})
const permissionFormRef = ref()

// 加载权限列表
const loadPermissions = async () => {
  try {
    const response = await http.get('/permission/permissions')
    if (response.ok) {
      const data = await response.json()
      permissions.value = data.data || []
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '加载权限列表失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载权限列表失败')
  }
}

// 创建权限
const handleCreatePermission = async () => {
  if (!permissionFormRef.value) return
  
  try {
    await permissionFormRef.value.validate()
    // 组合权限名称和操作
    const fullPermissionName = `${permissionForm.value.permissionName}:${permissionForm.value.operation}`
    const response = await http.post('/permission/permissions', {
      permissionName: fullPermissionName,
      permissionDescription: permissionForm.value.permissionDescription
    })
    
    if (response.ok) {
      ElMessage.success('权限创建成功')
      permissionDialogVisible.value = false
      permissionForm.value = { permissionName: '', operation: '', permissionDescription: '' }
      loadPermissions()
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '创建权限失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '创建权限失败')
  }
}

// 删除权限
const handleDeletePermission = async (permission: Permission) => {
  try {
    // 先检查权限的使用情况
    let usageInfo = null
    try {
      const usageResponse = await http.get(`/permission/permissions/${permission.permissionName}/usage`)
      if (usageResponse.ok) {
        const usageData = await usageResponse.json()
        usageInfo = usageData.data
      }
    } catch (error) {
      // 静默失败，继续删除流程
    }
    
    // 构建确认消息
    let force = false
    
    if (usageInfo && usageInfo.hasUsage) {
      const users = usageInfo.users || []
      const roles = usageInfo.roles || []
      
      let warningMessage = `该权限 "${permission.permissionName}" 当前被使用：\n\n`
      if (roles.length > 0) {
        warningMessage += `被 ${roles.length} 个角色使用：${roles.slice(0, 5).join(', ')}${roles.length > 5 ? ` 等 ${roles.length} 个` : ''}\n`
      }
      if (users.length > 0) {
        warningMessage += `被 ${users.length} 个用户使用：${users.slice(0, 5).join(', ')}${users.length > 5 ? ` 等 ${users.length} 个` : ''}\n`
      }
      warningMessage += '\n⚠️ 强制删除将同时移除所有相关的用户和角色关联，此操作不可恢复！'
      
      try {
        await ElMessageBox.confirm(
          warningMessage,
          '删除权限警告',
          {
            confirmButtonText: '强制删除',
            cancelButtonText: '取消',
            type: 'warning'
          }
        )
        force = true
      } catch {
        // 用户取消删除
        return
      }
    } else {
      // 如果没有使用情况，正常确认
      await ElMessageBox.confirm(
        `确定要删除权限 "${permission.permissionName}" 吗？`,
        '删除权限',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning'
        }
      )
    }
    
    const response = await http.delete('/permission/permissions', {
      permissionName: permission.permissionName,
      force: force
    })
    
    if (response.ok) {
      ElMessage.success(force ? '权限强制删除成功' : '权限删除成功')
      loadPermissions()
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '删除权限失败')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error?.message || '删除权限失败')
    }
  }
}

onMounted(() => {
  loadPermissions()
})
</script>

<template>
  <div class="permission-management">
    <div class="toolbar">
      <el-button type="primary" @click="permissionDialogVisible = true">创建权限</el-button>
    </div>
    <el-table :data="permissions" border stripe style="width: 100%">
      <el-table-column prop="permissionName" label="权限名称" width="250" />
      <el-table-column prop="permissionDescription" label="权限描述" />
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="scope">
          <el-button size="small" type="danger" @click="handleDeletePermission(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建权限对话框 -->
    <el-dialog v-model="permissionDialogVisible" title="创建权限" width="500px">
      <el-form ref="permissionFormRef" :model="permissionForm" label-width="100px">
        <el-form-item label="权限名称" prop="permissionName" :rules="[{ required: true, message: '请输入权限名称', trigger: 'blur' }]">
          <el-input v-model="permissionForm.permissionName" placeholder="请输入权限名称" />
        </el-form-item>
        <el-form-item label="操作" prop="operation" :rules="[{ required: true, message: '请选择操作类型', trigger: 'change' }]">
          <el-select v-model="permissionForm.operation" placeholder="请选择操作类型" style="width: 100%">
            <el-option label="读取 (read)" value="read" />
            <el-option label="写入 (write)" value="write" />
          </el-select>
        </el-form-item>
        <el-form-item label="权限描述" prop="permissionDescription">
          <el-input v-model="permissionForm.permissionDescription" type="textarea" placeholder="请输入权限描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="permissionDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreatePermission">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.permission-management {
  padding: 20px;
}

.toolbar {
  margin-bottom: 20px;
}
</style>

