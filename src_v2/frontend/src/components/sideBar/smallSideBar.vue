<script setup lang="ts">
import type { Component } from 'vue'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Expand, Fold, Paperclip } from '@element-plus/icons-vue'
import logoImg from '@/assets/logo.jpg'
import { useSidebarStore } from '@/stores/sidebar'

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
const sidebar = useSidebarStore()

/** 指针悬停：临时展开，移开即收起（P2-e 的浮层覆盖，热区就是 .sidebar 自身） */
const hovering = ref(false)
/** 显式展开（折叠按钮 / Enter / 触屏点按）：不随指针移开收起，与钉住同效但刷新失效 */
const openedByUser = ref(false)

/** 三条展开路径取并集；钉住是唯一跨会话保留的那条 */
const isExpanded = computed(() => sidebar.pinned || openedByUser.value || hovering.value)
const isPinned = computed(() => sidebar.pinned)

const toggleTitle = computed(() => (isExpanded.value ? '收起侧栏（Esc）' : '展开侧栏'))
const pinTitle = computed(() => (isPinned.value ? '取消钉住侧栏' : '钉住侧栏（移开指针也不收起）'))

/**
 * 展开/收起（折叠按钮与 Esc 共用）
 * 收起时一并解除钉住：按钮语义是「收起」，留着 pinned 会让点击看起来没生效；
 * 钉住本身有独立按钮和 aria-pressed，状态不会悄悄丢掉。
 */
const setCollapsed = () => {
  openedByUser.value = false
  hovering.value = false
  if (sidebar.pinned) sidebar.setPinned(false)
}

const toggleExpanded = () => {
  if (isExpanded.value) {
    setCollapsed()
  } else {
    openedByUser.value = true
  }
}

const togglePinned = () => {
  const next = !sidebar.pinned
  sidebar.setPinned(next)
  // 钉住只负责「常驻」；展开由 pinned 参与 isExpanded 计算。
  // 取消钉住时把临时展开一起清掉，否则点了取消看起来没反应（只剩 hover 还能撑住）。
  openedByUser.value = next
}

const handleEsc = () => {
  // 只在展开态吞掉 Esc，避免收起时把 Esc 拦下来（例如让弹窗/抽屉正常关闭）
  if (isExpanded.value) setCollapsed()
}

const toggleActive = (itemId: number) => {
  const targetRoute = props.menuItems.find(item => item.id === itemId)?.route || '/home'
  router.push(targetRoute)
}
</script>

<template>
  <!-- hover 展开是浮层覆盖（P2-e）：热区就是这条 .sidebar 自身——固定定位、满高、实心背景，
       60 → 148px 之间没有子元素或留白缝隙，所以指针不会落空导致展开/收起抖动。
       P2-b 起另外两条入口：折叠按钮（点击/Enter）与钉住（localStorage 持久化），三者取并集。 -->
  <el-aside
    class="sidebar"
    :class="{ expanded: isExpanded }"
    @mouseenter="hovering = true"
    @mouseleave="hovering = false"
    @keydown.esc="handleEsc"
  >
    <div class="sidebar-header">
      <div class="logo-container">
        <img :src="logoImg" alt="Kahuna Logo" class="logo" />
      </div>
      <!-- 展开入口单独成一个按钮：图标本身点击是导航，不能兼职开关。
           放在 header 是为了 Tab 顺序够得到（DOM 里在菜单项之前），
           键盘用户可以「先展开再浏览」，不必先摸黑穿完一排图标。 -->
      <button
        type="button"
        class="rail-toggle"
        aria-controls="sidebar-primary-nav"
        :aria-expanded="isExpanded ? 'true' : 'false'"
        aria-label="展开或收起侧栏"
        :title="toggleTitle"
        @click="toggleExpanded"
      >
        <el-icon :size="16">
          <component :is="isExpanded ? Fold : Expand" />
        </el-icon>
      </button>
    </div>

    <el-scrollbar class="sidebar-scrollbar">
      <nav id="sidebar-primary-nav" class="menu-items" aria-label="主导航">
        <button
          v-for="item in props.menuItems"
          :key="item.id"
          type="button"
          class="menu-item"
          :class="{ active: item.active }"
          :aria-current="item.active ? 'page' : undefined"
          @click="toggleActive(item.id)"
        >
          <span class="menu-icon-container">
            <el-icon :size="20">
              <component :is="item.icon" />
            </el-icon>
          </span>
          <span class="menu-title" :class="{ show: isExpanded }">{{ item.label }}</span>
        </button>
      </nav>
    </el-scrollbar>

    <!-- 钉住：常驻展开且跨会话保留（kahuna_sidebar_pinned）。
         aria-label 固定、状态交给 aria-pressed，读屏播报是「钉住侧栏，已按下」而不是标签乱跳。 -->
    <div class="sidebar-footer">
      <button
        type="button"
        class="rail-pin"
        :aria-pressed="isPinned ? 'true' : 'false'"
        aria-label="钉住侧栏"
        :title="pinTitle"
        @click="togglePinned"
      >
        <el-icon :size="16"><Paperclip /></el-icon>
      </button>
    </div>
  </el-aside>
</template>

<style scoped>
.sidebar {
  width: 60px;
  height: 100dvh;
  position: fixed;
  top: 0;
  left: 0;
  /* 层级：内容区（含 .main-header 的 backdrop-filter 栈上下文、el-table 固定列 z-index 2/3）
     都在这条线之下；EP 的 dialog/drawer/message 浮层是 JS 动态给的 2000+，仍在轨道之上。
     展开态因此是「盖住内容」而不是「被内容盖住」，且不会压住弹窗。 */
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid color-mix(in srgb, var(--k-color-primary) 16%, var(--k-color-border));
  background: linear-gradient(185deg, #0e2348 0%, #102a59 45%, #143d7a 100%);
  /* 收起态只留一条贴边的淡投影，不暗示「有浮层」 */
  box-shadow: 4px 0 22px rgba(2, 8, 23, 0.32);
  transition: width 0.24s ease, box-shadow 0.24s ease;
}

/* hover 展开 = 浮层覆盖（P2-e）：内容区宽度不变，靠投影把「盖在内容上」读出来。
   轨道本身在两套主题下都是深蓝渐变，所以阴影用深色；浅色主题下背景亮，反差更强。 */
.sidebar.expanded {
  width: 148px;
  box-shadow:
    10px 0 34px rgba(2, 8, 23, 0.46),
    4px 0 10px rgba(2, 8, 23, 0.3);
}

/* 深色主题的内容底色本身已经很暗（#1b1a2b），同一条深色投影几乎看不出来
   （实测距边 2px 只低 7.7 级亮度）。这一档单独加重到能读出来；只改投影，不动轨道配色与渐变。 */
[data-theme='dark'] .sidebar.expanded {
  box-shadow:
    14px 0 44px rgba(0, 0, 0, 0.72),
    6px 0 14px rgba(0, 0, 0, 0.46);
}

.sidebar-header {
  padding: 14px 0 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
}

.logo-container {
  width: 40px;
  height: 40px;
  border-radius: var(--k-radius-sm);
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

/* 展开入口 / 钉住：与图标项同一套白透明度，不加新色相（轨道配色与渐变保持原样） */
.rail-toggle,
.rail-pin {
  width: 40px;
  height: 26px;
  border: 0;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.82);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}

.rail-toggle:hover,
.rail-pin:hover {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.rail-pin[aria-pressed='true'] {
  background: rgba(255, 255, 255, 0.3);
  color: #fff;
}

/* 深色轨道上 --k-color-primary 的描边对比度不足，键盘聚焦给一圈白环 */
.rail-toggle:focus-visible,
.rail-pin:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.9);
  outline-offset: 2px;
}

.sidebar-scrollbar {
  flex: 1;
  min-height: 0;
}

.sidebar-footer {
  padding: 8px 0 10px;
  display: flex;
  justify-content: center;
  border-top: 1px solid rgba(255, 255, 255, 0.15);
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
  color: var(--k-color-text-inverse);
  box-shadow: 0 8px 16px rgba(33, 110, 255, 0.38);
}

/* 全局 :focus-visible 的描边是品牌蓝，压在深蓝渐变上几乎看不见；键盘走查要求「看得见焦点」 */
.menu-item:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.9);
  outline-offset: 2px;
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
