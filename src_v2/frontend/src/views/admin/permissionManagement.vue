<script setup lang="ts">
import { ref } from 'vue'
import RoleManagement from './permissionManagement/components/RoleManagement.vue'
import PermissionManagement from './permissionManagement/components/PermissionManagement.vue'
import UserRoleManagement from './permissionManagement/components/UserRoleManagement.vue'
import HierarchyTreeView from './permissionManagement/components/HierarchyTreeView.vue'

const activeTab = ref('roles')
const roleManagementRef = ref<InstanceType<typeof RoleManagement>>()
const hierarchyTreeViewRef = ref<InstanceType<typeof HierarchyTreeView>>()

// 当角色管理刷新时，也刷新层级树
const handleRoleRefresh = () => {
  hierarchyTreeViewRef.value?.loadHierarchyTree()
}
</script>

<template>
  <div class="permission-management">
    <el-tabs v-model="activeTab" class="permission-tabs">
      <!-- 角色管理 -->
      <el-tab-pane label="角色管理" name="roles">
        <RoleManagement ref="roleManagementRef" @refresh="handleRoleRefresh" />
      </el-tab-pane>

      <!-- 权限管理 -->
      <el-tab-pane label="权限管理" name="permissions">
        <PermissionManagement />
      </el-tab-pane>

      <!-- 用户角色关联 -->
      <el-tab-pane label="用户角色关联" name="userRoles">
        <UserRoleManagement />
      </el-tab-pane>

      <!-- 角色层级关系视图 -->
      <el-tab-pane label="角色层级关系" name="hierarchy">
        <HierarchyTreeView ref="hierarchyTreeViewRef" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.permission-management {
  padding: 20px;
}

.permission-tabs {
  min-height: 600px;
}
</style>
