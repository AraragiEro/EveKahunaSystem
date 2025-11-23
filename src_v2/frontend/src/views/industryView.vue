<script setup lang="ts">
import { ref } from 'vue'
import SidebarLayout from '../components/SidebarLayout.vue'
import mainSidebar from '../components/sideBar/mainSidebar.vue'
import { useAuthStore } from '@/stores/auth'
const authStore = useAuthStore()
const segmentItems = ref<{index: number, label: string, route: string}[]>([]);

const userRoles = authStore.user?.roles || []
segmentItems.value.push({index: 1, label: '总览视图', route: '/industry/overview'})
if (userRoles.includes('vip_alpha')) {
  segmentItems.value.push({index: 2, label: '库存管理', route: '/industry/assetView'})
}
segmentItems.value.push({index: 3, label: '工业计划', route: '/industry/industryPlan'})
segmentItems.value.push({index: 4, label: '报表空间', route: '/industry/flowDecomposition'})

</script>

<template>
  <SidebarLayout 
    :aside-width="180" 
    :menu-items="segmentItems"
    :sidebar-component="mainSidebar"
  >
    <router-view />
  </SidebarLayout>
</template>

<style scoped>
</style>