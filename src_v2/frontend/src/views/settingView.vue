<script setup lang="ts">
import { ref, computed } from 'vue'
import SidebarLayout from '../components/SidebarLayout.vue'
import settingSidebar from '../components/sideBar/mainSidebar.vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const haveAlphaRole = computed(() => {
    return authStore.user?.roles.includes('vip_alpha') || false
})

const menuItems = computed(() => {
    const items: {index: number, label: string, route: string}[] = []
    if (haveAlphaRole.value) {
        items.push({ index: 1, label: '角色设置', route: '/setting/characterSetting'})
    }
    items.push({ index: 2, label: '账号配置', route: '/setting/accountSetting'})
    return items
})

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