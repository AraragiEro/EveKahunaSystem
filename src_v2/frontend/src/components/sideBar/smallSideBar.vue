<script setup lang="ts">
import type { Component } from 'vue'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import logoImg from '@/assets/logo.jpg'

interface MenuItem {
  id: number
  icon: Component
  label: string
  active: boolean
  route: string
}

interface Props {
  menuItems: MenuItem[]
}

const props = defineProps<Props>()
const router = useRouter()
const isExpanded = ref(false)

const toggleActive = (itemId: number) => {
  const targetRoute = props.menuItems.find(item => item.id === itemId)?.route || '/home'
  router.push(targetRoute)
}
</script>

<template>
  <el-aside
    class="sidebar"
    :class="{ expanded: isExpanded }"
    @mouseenter="isExpanded = true"
    @mouseleave="isExpanded = false"
  >
    <div class="sidebar-header">
      <div class="logo-container">
        <img :src="logoImg" alt="Kahuna Logo" class="logo" />
      </div>
    </div>

    <el-scrollbar class="sidebar-scrollbar">
      <div class="menu-items">
        <button
          v-for="item in props.menuItems"
          :key="item.id"
          type="button"
          class="menu-item"
          :class="{ active: item.active }"
          @click="toggleActive(item.id)"
        >
          <span class="menu-icon-container">
            <el-icon :size="20">
              <component :is="item.icon" />
            </el-icon>
          </span>
          <span class="menu-title" :class="{ show: isExpanded }">{{ item.label }}</span>
        </button>
      </div>
    </el-scrollbar>
  </el-aside>
</template>

<style scoped>
.sidebar {
  width: 60px;
  height: 100dvh;
  position: fixed;
  top: 0;
  left: 0;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid color-mix(in srgb, var(--k-color-primary) 16%, var(--k-color-border));
  background: linear-gradient(185deg, #0e2348 0%, #102a59 45%, #143d7a 100%);
  box-shadow: 4px 0 22px rgba(2, 8, 23, 0.32);
  transition: width 0.24s ease;
}

.sidebar.expanded {
  width: 148px;
}

.sidebar-header {
  padding: 14px 0;
  display: flex;
  justify-content: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
}

.logo-container {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.16);
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo {
  width: 32px;
  height: 32px;
  object-fit: contain;
  border-radius: 8px;
}

.sidebar-scrollbar {
  flex: 1;
  min-height: 0;
}

.menu-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 8px 20px;
}

.menu-item {
  width: 100%;
  height: 48px;
  border: 0;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  padding: 0 12px;
  color: rgba(255, 255, 255, 0.84);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.menu-item:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.16);
}

.menu-item.active {
  background: linear-gradient(135deg, #2b74ff 0%, #39b7ff 100%);
  color: white;
  box-shadow: 0 8px 16px rgba(33, 110, 255, 0.38);
}

.menu-icon-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
}

.menu-title {
  margin-left: 10px;
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  opacity: 0;
  transform: translateX(-6px);
  transition: all 0.24s ease;
}

.menu-title.show {
  opacity: 1;
  transform: translateX(0);
}
</style>
