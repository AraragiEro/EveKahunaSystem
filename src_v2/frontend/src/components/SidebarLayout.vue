<script setup lang="ts">
import { computed, type Component } from 'vue'

// 定义菜单项接口
export interface MenuItem {
  index: number
  label: string
  route: string
  active?: boolean
}

interface Props {
  asideWidth?: string | number
  menuItems: MenuItem[]
  sidebarComponent: Component | string
}

const props = withDefaults(defineProps<Props>(), {
  asideWidth: '220px'
})

// 计算侧边栏宽度样式
const asideWidthStyle = computed(() => {
  if (typeof props.asideWidth === 'number') {
    return `${props.asideWidth}px`
  }
  return props.asideWidth
})
</script>

<template>
  <div class="sidebar-layout">
    <el-aside 
      :width="asideWidthStyle" 
      class="sidebar-aside"
    >
      <component :is="sidebarComponent" :menuItems="menuItems" />
    </el-aside>

    <el-scrollbar class="sidebar-content">
      <div class="content-panel">
        <slot />
      </div>
    </el-scrollbar>
  </div>
</template>

<style scoped>
.sidebar-layout {
  height: calc(98vh - 60px - 64px);
  width: 100%;
  overflow: hidden;
  background: #f5f7fa;
  display: flex;
  flex-direction: row;
}

.sidebar-aside {
  min-height: calc(96vh - 60px - 64px);
  height: 100%;
  background: #ffffff;
  border-right: 1px solid #e5e7eb;
  padding: 16px 0;
  overflow-y: auto;
  overflow-x: hidden;
  flex-shrink: 0;
}

.sidebar-content {
  flex: 1;
  height: 100%;
  min-height: calc(96vh - 60px - 64px);
  padding: 12px;
  overflow: hidden;
  min-width: 0;
}

.content-panel {
  width: 100%;
  min-height: calc(96vh - 60px - 64px - 12px);
  height: 100%;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  padding: 12px;
  overflow-y: auto;
  overflow-x: hidden;
  box-sizing: border-box;
}

/* 优化滚动条样式 */
.content-panel::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.content-panel::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.content-panel::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.content-panel::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

.sidebar-aside::-webkit-scrollbar {
  width: 6px;
}

.sidebar-aside::-webkit-scrollbar-track {
  background: #f9fafb;
}

.sidebar-aside::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 3px;
}

.sidebar-aside::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}
</style>

