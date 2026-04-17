<script setup lang="ts">
import { computed, type Component } from 'vue'

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
  asideWidth: '220px',
})

const asideWidthStyle = computed(() => {
  if (typeof props.asideWidth === 'number') return `${props.asideWidth}px`
  return props.asideWidth
})
</script>

<template>
  <div class="sidebar-layout">
    <el-aside :width="asideWidthStyle" class="sidebar-aside">
      <component :is="sidebarComponent" :menu-items="menuItems" />
    </el-aside>

    <main class="content-host">
      <div class="content-panel">
        <slot />
      </div>
    </main>
  </div>
</template>

<style scoped>
.sidebar-layout {
  height: 100%;
  min-height: 0;
  width: 100%;
  display: flex;
  background: transparent;
  overflow: hidden;
  gap: 12px;
}

.sidebar-aside {
  height: 100%;
  min-height: 0;
  overflow: auto;
  border-radius: var(--k-radius-lg);
  border: 1px solid var(--k-color-border);
  background: var(--k-color-surface);
}

.content-host {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.content-panel {
  height: 100%;
  min-height: 0;
  overflow: auto;
  border-radius: var(--k-radius-lg);
  border: 1px solid var(--k-color-border);
  background: var(--k-color-surface);
  box-shadow: var(--k-shadow-sm);
  padding: 12px;
}

@media (max-width: 900px) {
  .sidebar-layout {
    gap: 8px;
  }

  .content-panel {
    padding: 8px;
  }
}
</style>
