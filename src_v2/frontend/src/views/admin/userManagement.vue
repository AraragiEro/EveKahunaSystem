<script setup lang="ts">
/**
 * 管理台 · 用户管理
 * ---------------------------------------------------------------
 * 本页此前只有一个 `<h1>用户管理</h1>`，但它是管理台的第一项。
 * 最小可用实现：直接复用「权限管理 → 用户角色关联」里已经写好的
 * UserRoleManagement 组件（用户列表 GET /permission/users +
 * 角色增删 POST/DELETE /permission/users/roles），
 * 不复制一套逻辑，也不新增后端接口。
 */
import UserRoleManagement from './permissionManagement/components/UserRoleManagement.vue'
</script>

<template>
  <div class="user-management">
    <div class="header">
      <h2>用户管理</h2>
    </div>
    <p class="page-hint">
      列出网站全部账号。点某一行的「管理角色」即可查看并增删该用户的角色，
      与「权限管理 → 用户角色关联」是同一份数据。
    </p>

    <UserRoleManagement />
  </div>
</template>

<style scoped>
/* 内层 UserRoleManagement 自带 20px 内边距，这里只负责标题的 20px 对齐 */
.user-management {
  padding: 0;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 20px 0;
}

.header h2 {
  margin: 0;
}

.page-hint {
  margin: 0;
  padding: 8px 20px 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--k-color-text-secondary);
}
</style>