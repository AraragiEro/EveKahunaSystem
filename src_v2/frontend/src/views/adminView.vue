<script setup lang="ts">
import { ref } from 'vue'
import SidebarLayout from '../components/SidebarLayout.vue'
import settingSidebar from '../components/sideBar/mainSidebar.vue'

const menuItems = ref([
  { index: 1, label: '用户管理', route: '/admin/userManagement'},
  { index: 2, label: '权限管理', route: '/admin/permissionManagement'},
  { index: 3, label: '邀请码管理', route: '/admin/inviteCodeManagement'},
  { index: 4, label: '会员管理', route: '/admin/vipManagement'}
])

</script>

<template>
  <SidebarLayout 
    :aside-width="220" 
    :menu-items="menuItems"
    :sidebar-component="settingSidebar"
  >
    <router-view />
  </SidebarLayout>
</template>