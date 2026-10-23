<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch, type Component } from 'vue'
import { useRoute } from 'vue-router'
import { Close, Menu } from '@element-plus/icons-vue'
import { useSidebarStore } from '@/stores/sidebar'

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
  /**
   * 内容区是否由外层负责滚动（默认 true）。
   * 报表空间这类页面要自己管理滚动（表格单独滚、工具栏可收起），传 false 关掉外层滚动条。
   */
  scrollable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  asideWidth: '220px',
  scrollable: true,
})

const asideWidthStyle = computed(() => {
  if (typeof props.asideWidth === 'number') return `${props.asideWidth}px`
  return props.asideWidth
})

/**
 * ≤1024 的二级侧栏抽屉（P2-C）
 * ---------------------------------------------------------------
 * 接在 P2-b 那套状态机上：状态存在 useSidebarStore（drawerOpen），
 * 不新建第二套侧栏 store。宽屏（>1024）下 drawerOpen 永远为 false 且
 * 抽屉相关的 DOM/样式全部 display:none，所以 1920/2560 的布局一个像素都不动。
 *
 * 收起路径三条，与 P2-b 的语义对齐：
 *   1. 再点一次汉堡（toggle）；
 *   2. Esc（全局，只在抽屉开着时响应 —— 不开时把 Esc 让给弹窗/抽屉）；
 *   3. 点遮罩，或点二级菜单项跳转后自动收（watch route.path）。
 */
const sidebar = useSidebarStore()
const route = useRoute()

const drawerOpen = computed(() => sidebar.drawerOpen)

/** 抽屉关着时，汉堡右边显示当前二级页名，否则窄屏用户不知道自己在哪一块 */
const currentLabel = computed(() => {
  const hit = props.menuItems.find(item => item.route && route.path.startsWith(item.route))
  return hit?.label ?? ''
})

const toggleTitle = computed(() => (drawerOpen.value ? '收起菜单（Esc）' : '展开菜单'))

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && sidebar.drawerOpen) sidebar.closeDrawer()
}

// 跳转到别的二级页后自动收起：抽屉是浮层，跳完还挡着内容没有道理
watch(
  () => route.path,
  () => {
    if (sidebar.drawerOpen) sidebar.closeDrawer()
  },
)

onMounted(() => window.addEventListener('keydown', handleKeydown))
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div class="sidebar-layout">
    <!-- ≤1024 才有：汉堡 + 当前页名。宽屏 display:none，不参与 1920 的布局 -->
    <div class="aside-drawer-bar">
      <button
        type="button"
        class="aside-drawer-toggle"
        aria-controls="secondary-nav"
        :aria-expanded="drawerOpen ? 'true' : 'false'"
        aria-label="展开或收起二级菜单"
        :title="toggleTitle"
        @click="sidebar.toggleDrawer()"
      >
        <el-icon :size="18">
          <component :is="drawerOpen ? Close : Menu" />
        </el-icon>
      </button>
      <span class="aside-drawer-title">{{ currentLabel }}</span>
    </div>

    <!-- 遮罩：只在 ≤1024 且打开时可见（CSS 控制显示，宽屏恒 display:none） -->
    <div
      v-if="drawerOpen"
      class="aside-drawer-mask"
      aria-hidden="true"
      @click="sidebar.closeDrawer()"
    />

    <el-aside
      id="secondary-nav"
      :width="asideWidthStyle"
      class="sidebar-aside"
      :class="{ 'is-drawer-open': drawerOpen }"
    >
      <component :is="sidebarComponent" :menu-items="menuItems" />
    </el-aside>

    <main class="content-host">
      <div class="content-panel" :class="{ 'content-panel--fixed': !scrollable }">
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

/* 页面自己管理滚动：外层不出滚动条，避免和表格滚动条打架 */
.content-panel--fixed {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  /* 页面底压暗一档，里面的模块卡片才「浮」得出来 */
  background: var(--k-color-surface-sunken);
  padding: 10px;
}

/* 窄屏抽屉的入口与遮罩：宽屏下不渲染、不占位（display:none 的 flex 子项
   不参与布局），所以 1920/2560 的结构与改动前完全一致。 */
.aside-drawer-bar,
.aside-drawer-mask {
  display: none;
}

@media (max-width: 900px) {
  .sidebar-layout {
    gap: 8px;
  }

  .content-panel {
    padding: 8px;
  }
}

/* ── P2-C：≤1024 二级侧栏收成抽屉 ─────────────────────────────────────
   宽屏（>1024）完全没有下面的规则命中：汉堡条与遮罩默认 display:none，
   侧栏仍是参与 flex 的静态 el-aside，所以 1920/2560 的版式不变。

   为什么抽屉宽度不覆盖 el-aside 的内联 width：el-aside 的宽度是组件
   通过 :width 写进 style 属性的内联样式，媒体查询压不过它；而 180/220px
   在抽屉场景本来就合适，宁可不动，也不为它引入 !important。 */
@media (max-width: 1024px) {
  /* 竖排：汉堡条在上，内容区占满剩下高度；侧栏是 fixed 抽屉，不占位 */
  .sidebar-layout {
    flex-direction: column;
    gap: 0;
  }

  .aside-drawer-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 0 0 auto;
    padding: 4px 2px 8px;
  }

  .aside-drawer-toggle {
    width: 34px;
    height: 34px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--k-color-border);
    border-radius: var(--k-radius-sm);
    background: var(--k-color-surface);
    color: var(--k-color-text);
    box-shadow: var(--k-shadow-sm);
    cursor: pointer;
    transition: border-color 0.2s ease, color 0.2s ease;
    /* 抽屉打开时抽屉会盖住这条汉堡（抽屉 left 从 60px 起）：
       抬到抽屉之上，否则「再点一次汉堡收起」这条最直觉的路径摸不到，
       只能靠 Esc 或点遮罩。960 > 抽屉的 950。 */
    position: relative;
    z-index: 960;
  }

  .aside-drawer-toggle:hover {
    border-color: color-mix(in srgb, var(--k-color-primary) 40%, var(--k-color-border));
    color: var(--k-color-primary);
  }

  .aside-drawer-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--k-color-text-secondary);
  }

  /* 遮罩从图标轨右侧铺满：左侧 60px 的一级轨道仍可点击，不被挡住 */
  .aside-drawer-mask {
    display: block;
    position: fixed;
    inset: 0 0 0 var(--k-rail-w, 60px);
    z-index: 940;
    background: rgba(2, 8, 23, 0.36);
  }

  .sidebar-aside {
    position: fixed;
    top: 0;
    left: var(--k-rail-w, 60px);
    height: 100dvh;
    z-index: 950;
    border-radius: 0 var(--k-radius-lg) var(--k-radius-lg) 0;
    /* 收起态整体平移到视口左侧之外，且不可点；不做 display:none，
       否则 0.24s 的入场动画没有可过渡的起点。 */
    transform: translateX(calc(-100% - var(--k-rail-w, 60px)));
    transition: transform 0.24s ease, box-shadow 0.24s ease;
    box-shadow: none;
    pointer-events: none;
  }

  .sidebar-aside.is-drawer-open {
    transform: translateX(0);
    box-shadow: 12px 0 34px rgba(2, 8, 23, 0.28);
    pointer-events: auto;
  }

  [data-theme='dark'] .sidebar-aside.is-drawer-open {
    box-shadow: 14px 0 44px rgba(0, 0, 0, 0.6);
  }
}
</style>
