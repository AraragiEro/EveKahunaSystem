<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import settingSidebar from '../components/sideBar/mainSidebar.vue'

const router = useRouter()

const menuItems = ref([
  { index: 1, label: '个人信息', route: '/setting/userSetting'},
  { index: 2, label: '工业配置', route: '/setting/industrySetting'}
])



</script>

<template>
  <el-container class="setting-view">
    <el-aside width="150px">
      <settingSidebar :menuItems="menuItems" />
    </el-aside>

    <el-container class="setting-container">
      <router-view />
    </el-container>
  </el-container>
</template>

<style scoped>
/* 方法1: 通过CSS变量设置菜单项高度 */
.custom-menu {
  --el-menu-item-height: 50px; /* 设置菜单项高度为60px */
}

.setting-view {
  height: 100%;
}

.setting-container {
  padding: 20px;
}

</style>