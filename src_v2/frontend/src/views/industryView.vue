<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import SidebarLayout from '../components/SidebarLayout.vue'
import mainSidebar from '../components/sideBar/mainSidebar.vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const route = useRoute()
const segmentItems = ref<{ index: number; label: string; route: string }[]>([])
const userRoles = authStore.user?.roles || []

// 报表空间自己管滚动（表格单独滚 + 工具栏可收起），其余子页沿用外层滚动
const scrollable = computed(() => route.name !== 'flowDecomposition')

if (userRoles.includes('vip_alpha')) {
  segmentItems.value.push({ index: 1, label: '库存管理', route: '/industry/assetView' })
}
segmentItems.value.push({ index: 2, label: '工业计划', route: '/industry/industryPlan' })
segmentItems.value.push({ index: 3, label: '报表空间', route: '/industry/flowDecomposition' })
</script>

<template>
  <SidebarLayout
    :aside-width="180"
    :menu-items="segmentItems"
    :sidebar-component="mainSidebar"
    :scrollable="scrollable"
  >
    <router-view />
  </SidebarLayout>
</template>
