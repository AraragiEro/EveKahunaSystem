<script setup lang="ts">
import { ref } from 'vue'
import SidebarLayout from '../components/SidebarLayout.vue'
import mainSidebar from '../components/sideBar/mainSidebar.vue'

const segmentItems = ref<{ index: number, label: string, route: string }[]>([])

// 配置菜单项
segmentItems.value.push({ index: 1, label: '总览', route: '/home/overview' })
segmentItems.value.push({ index: 2, label: '历史', route: '/home/history' })
</script>

<template>
  <SidebarLayout :aside-width="180" :menu-items="segmentItems" :sidebar-component="mainSidebar">
    <router-view />
  </SidebarLayout>
</template>

<style scoped></style>
