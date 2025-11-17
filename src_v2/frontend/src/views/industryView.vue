<script setup lang="ts">
import { ref } from 'vue'
import SidebarLayout from '../components/SidebarLayout.vue'
import mainSidebar from '../components/sideBar/mainSidebar.vue'

const segmentItems = ref([
  {index: 1, label: '总览视图', route: '/industry/overview'},
  {index: 2, label: '库存管理', route: '/industry/assetView'},
  {index: 3, label: '工业计划', route: '/industry/industryPlan'},
  {index: 4, label: '报表空间', route: '/industry/flowDecomposition'}
])

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