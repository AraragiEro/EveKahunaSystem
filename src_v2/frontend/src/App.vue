<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDown,
  ChatLineRound,
  Cpu,
  Document,
  House,
  Monitor,
  Moon,
  Opportunity,
  PieChart,
  Setting,
  Sunny,
  Tickets,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useHelpStore } from '@/stores/help'
import { useEdition } from '@/composables/useEdition'
import { useThemeStore, type ThemeMode } from '@/stores/theme'
import smallSideBar from './components/sideBar/smallSideBar.vue'
import HelpDrawer from './components/HelpDrawer.vue'
import VipPricingDialog from './components/VipPricingDialog.vue'
import githubIcon from '@/assets/github-mark.svg'
import aifadianLogo from '@/assets/横版-白底-透明背景.png'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const helpStore = useHelpStore()
const themeStore = useThemeStore()
const { isEnterprise } = useEdition()

const GITHUB_REPO_URL = 'https://github.com/AraragiEro/EveKahunaSystem.git'
const publicPages = ['login', 'landing', 'announcements', 'forbidden', 'characterAuthClose', 'publicStorage', 'publicWorkflow', 'allianceContract']

const donateLink = computed(() => import.meta.env.VITE_DONATE_LINK as string | undefined)
const showDonateButton = computed(() => !!donateLink.value)
const isPublicPage = computed(() => publicPages.includes(route.name as string))

const themeIconMap = {
  light: Sunny,
  dark: Moon,
  system: Monitor,
} as const

const currentThemeIcon = computed(() => themeIconMap[themeStore.mode])
type MenuIconComponent =
  | typeof Tickets
  | typeof House
  | typeof Cpu
  | typeof PieChart
  | typeof Opportunity
  | typeof ChatLineRound
  | typeof Setting

const menuItems = computed(() => {
  const items: { id: number; icon: MenuIconComponent; label: string; active: boolean; route: string }[] = []
  const currentPath = router.currentRoute.value.path
  const userRoles = authStore.user?.roles || []
  let idIndex = 1

  items.push({
    id: idIndex++,
    icon: Tickets,
    label: 'TODO',
    active: currentPath === '/todolist' || currentPath === '/',
    route: '/todolist',
  })

  if (userRoles.includes('vip_alpha') || userRoles.includes('vip_omega')) {
    items.push({
      id: idIndex++,
      icon: House,
      label: '总览',
      active: currentPath.startsWith('/home'),
      route: '/home',
    })
  }

  if (userRoles.includes('user')) {
    items.push({
      id: idIndex++,
      icon: Cpu,
      label: '工业',
      active: currentPath.startsWith('/industry'),
      route: '/industry',
    })
  }

  if (isEnterprise && userRoles.includes('vip_omega')) {
    items.push({
      id: idIndex++,
      icon: PieChart,
      label: '市场分析',
      active: currentPath.startsWith('/market'),
      route: '/market',
    })
  }

  if (userRoles.includes('user')) {
    items.push({
      id: idIndex++,
      icon: Opportunity,
      label: '实用工具',
      active: currentPath === '/utils',
      route: '/utils',
    })
    items.push({
      id: idIndex++,
      icon: ChatLineRound,
      label: '留言板',
      active: currentPath === '/messageBoard',
      route: '/messageBoard',
    })
    items.push({
      id: idIndex++,
      icon: Setting,
      label: '设置',
      active: currentPath.startsWith('/setting'),
      route: '/setting',
    })
  }

  if (userRoles.includes('admin')) {
    items.push({
      id: idIndex++,
      icon: Cpu,
      label: '管理台',
      active: currentPath.startsWith('/admin'),
      route: '/admin',
    })
  }

  return items
})

const hasAlphaSubscription = computed(() => (authStore.user?.roles || []).includes('vip_alpha'))
const hasOmegaSubscription = computed(() => (authStore.user?.roles || []).includes('vip_omega'))
const isNonVip = computed(() => !hasAlphaSubscription.value && !hasOmegaSubscription.value)
const subscriptionEndDate = computed(() => authStore.user?.vipEndDate || null)
const currentTime = ref(Date.now())
const vipDialogVisible = ref(false)

const openGitHub = () => {
  window.open(GITHUB_REPO_URL, '_blank')
}

const openDonate = () => {
  if (donateLink.value) {
    window.open(donateLink.value, '_blank')
  }
}

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}

const isExpired = (endDateStr: string | null | undefined): boolean => {
  if (!endDateStr) return true
  const endDate = new Date(endDateStr)
  return endDate.getTime() <= currentTime.value
}

const getRemainingTimeText = (endDateStr: string | null | undefined): string => {
  if (!endDateStr) return ''
  const diff = new Date(endDateStr).getTime() - currentTime.value
  if (diff <= 0) return ''
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
  if (days > 0) return `剩余 ${days} 天 ${hours} 小时`
  if (hours > 0) return `剩余 ${hours} 小时 ${minutes} 分钟`
  return `剩余 ${minutes} 分钟`
}

const getRemainingTimeTagType = (endDateStr: string | null | undefined): 'danger' | 'warning' | 'success' | 'info' => {
  if (!endDateStr) return 'info'
  const diff = new Date(endDateStr).getTime() - currentTime.value
  if (diff <= 0) return 'danger'
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  if (days < 1) return 'danger'
  if (days < 7) return 'warning'
  return 'success'
}

const cycleTheme = () => {
  const next: Record<ThemeMode, ThemeMode> = {
    light: 'dark',
    dark: 'system',
    system: 'light',
  }
  themeStore.setMode(next[themeStore.mode])
}

const setThemeMode = (mode: ThemeMode) => {
  themeStore.setMode(mode)
}

const themeModeLabel = computed(() => {
  if (themeStore.mode === 'light') return '浅色'
  if (themeStore.mode === 'dark') return '深色'
  return '跟随系统'
})

const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'F1') {
    event.preventDefault()
    helpStore.openHelp()
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'h') {
    event.preventDefault()
    helpStore.openHelp()
  }
}

let timeUpdateInterval: number | null = null

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  timeUpdateInterval = window.setInterval(() => {
    currentTime.value = Date.now()
  }, 60000)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
  if (timeUpdateInterval !== null) {
    clearInterval(timeUpdateInterval)
  }
})
</script>

<template>
  <div class="kahuna-container">
    <div v-if="isPublicPage" class="public-page-scroll">
      <router-view />
    </div>

    <el-container v-else-if="authStore.isAuthenticated" class="app-shell">
      <smallSideBar :menu-items="menuItems" />

      <el-container class="main-container">
        <el-header class="main-header">
          <div class="header-content">
            <div class="header-title">
              <h2>Kahuna-System V1.5.2</h2>
              <el-tag :type="isEnterprise ? 'success' : 'info'" size="small" class="edition-tag">
                {{ isEnterprise ? '企业版' : '社区版' }}
              </el-tag>
              <el-tag v-if="hasAlphaSubscription && !hasOmegaSubscription" type="warning" size="small" class="edition-tag">
                Alpha 订阅
              </el-tag>
              <el-tag
                v-if="hasAlphaSubscription && !hasOmegaSubscription && subscriptionEndDate && !isExpired(subscriptionEndDate)"
                :type="getRemainingTimeTagType(subscriptionEndDate)"
                size="small"
                class="edition-tag"
              >
                {{ getRemainingTimeText(subscriptionEndDate) }}
              </el-tag>
              <el-tag v-if="hasOmegaSubscription" type="danger" size="small" class="edition-tag">
                Omega 订阅
              </el-tag>
              <el-tag
                v-if="hasOmegaSubscription && subscriptionEndDate && !isExpired(subscriptionEndDate)"
                :type="getRemainingTimeTagType(subscriptionEndDate)"
                size="small"
                class="edition-tag"
              >
                {{ getRemainingTimeText(subscriptionEndDate) }}
              </el-tag>
              <el-button v-if="isNonVip" type="primary" size="small" @click="vipDialogVisible = true" class="edition-tag get-vip-button">
                获取 VIP
              </el-button>
            </div>

            <div class="header-actions">
              <el-button @click="cycleTheme" class="header-action-btn" :title="`切换主题（当前：${themeModeLabel}）`">
                <el-icon><component :is="currentThemeIcon" /></el-icon>
                <span class="btn-label">{{ themeModeLabel }}</span>
              </el-button>

              <el-button v-if="showDonateButton" @click="openDonate" title="支持作者" class="header-action-btn donate-button">
                <img :src="aifadianLogo" alt="爱发电" class="donate-icon" />
              </el-button>

              <el-button @click="openGitHub" title="打开 GitHub 仓库" class="header-action-btn github-btn">
                <img :src="githubIcon" alt="GitHub" class="github-icon" />
                <span class="btn-label">仓库</span>
              </el-button>

              <el-button @click="helpStore.openHelp" title="打开使用说明 (F1)" class="header-action-btn">
                <el-icon><Document /></el-icon>
                <span class="btn-label">指南</span>
              </el-button>

              <div class="user-info">
                <el-dropdown @command="handleLogout">
                  <span class="user-dropdown">
                    <el-avatar :size="32">{{ authStore.user?.username?.charAt(0)?.toUpperCase() }}</el-avatar>
                    <span class="username">{{ authStore.user?.username }}</span>
                    <el-icon><ArrowDown /></el-icon>
                  </span>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="logout">退出登录</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </div>
        </el-header>

        <el-main class="main-content">
          <div class="main-scroll">
            <router-view />
          </div>
        </el-main>

        <el-footer class="main-footer">
          <span>© 2026 Kahuna System</span>
        </el-footer>
      </el-container>
    </el-container>

    <HelpDrawer />
    <VipPricingDialog v-model="vipDialogVisible" />

    <div class="global-theme-switch">
      <el-dropdown trigger="click" @command="setThemeMode">
        <el-button circle class="theme-fab" :title="`主题：${themeModeLabel}`">
          <el-icon><component :is="currentThemeIcon" /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="light">浅色模式</el-dropdown-item>
            <el-dropdown-item command="dark">深色模式</el-dropdown-item>
            <el-dropdown-item command="system">跟随系统</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<style scoped>
.kahuna-container,
.app-shell {
  height: 100%;
  min-height: 100dvh;
  overflow: hidden;
}

.public-page-scroll {
  height: 100%;
  min-height: 100dvh;
  overflow: auto;
}

.main-container {
  margin-left: 60px;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: transparent;
}

.main-header {
  height: auto;
  min-height: 64px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--k-color-border);
  background: color-mix(in srgb, var(--k-color-surface) 92%, transparent);
  backdrop-filter: blur(10px);
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.header-title h2 {
  margin: 0;
  color: var(--k-color-text);
  font-size: 20px;
  font-weight: 700;
}

.edition-tag {
  border-radius: var(--k-radius-sm);
  border-color: var(--k-color-border);
}

.header-title :deep(.edition-tag) {
  background: var(--k-color-surface-soft) !important;
  color: var(--k-color-text-secondary) !important;
  border-color: var(--k-color-border) !important;
}

.header-title :deep(.edition-tag.el-tag--success) {
  background: color-mix(in srgb, var(--k-color-success) 16%, var(--k-color-surface-soft)) !important;
  color: var(--k-color-success) !important;
}

.header-title :deep(.edition-tag.el-tag--warning) {
  background: color-mix(in srgb, var(--k-color-warning) 16%, var(--k-color-surface-soft)) !important;
  color: var(--k-color-warning) !important;
}

.header-title :deep(.edition-tag.el-tag--danger) {
  background: color-mix(in srgb, var(--k-color-danger) 16%, var(--k-color-surface-soft)) !important;
  color: var(--k-color-danger) !important;
}

.header-title :deep(.edition-tag.el-tag--info) {
  background: color-mix(in srgb, var(--k-color-primary) 10%, var(--k-color-surface-soft)) !important;
  color: var(--k-color-primary) !important;
}

.get-vip-button {
  margin-left: 4px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.header-action-btn {
  border-radius: var(--k-radius-sm);
  border-color: var(--k-color-border);
  color: var(--k-color-text-secondary);
  background: var(--k-color-surface);
  box-shadow: var(--k-shadow-sm);
}

.header-action-btn:hover {
  border-color: color-mix(in srgb, var(--k-color-primary) 40%, var(--k-color-border));
  color: var(--k-color-text);
}

.btn-label {
  font-size: 13px;
}

.github-icon {
  width: 16px;
  height: 16px;
}

.donate-icon {
  width: auto;
  height: 24px;
  display: block;
}

.user-info {
  margin-left: 6px;
}

.user-dropdown {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--k-radius-sm);
}

.user-dropdown:hover {
  background: var(--k-color-surface-soft);
}

.username {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--k-color-text-secondary);
}

.main-content {
  flex: 1;
  min-height: 0;
  padding: 16px;
  overflow: hidden;
}

.main-scroll {
  height: 100%;
  overflow: auto;
  border-radius: var(--k-radius-lg);
}

.main-footer {
  height: 42px;
  flex-shrink: 0;
  border-top: 1px solid var(--k-color-border);
  color: var(--k-color-text-secondary);
  background: color-mix(in srgb, var(--k-color-surface) 96%, transparent);
}

.global-theme-switch {
  position: fixed;
  right: 14px;
  bottom: 14px;
  z-index: 3000;
}

.theme-fab {
  width: 40px;
  height: 40px;
  border: 1px solid var(--k-color-border);
  background: var(--k-color-surface);
  color: var(--k-color-text);
  box-shadow: var(--k-shadow-md);
}

@media (max-width: 900px) {
  .main-container {
    margin-left: 60px;
  }

  .main-content {
    padding: 10px;
  }

  .btn-label {
    display: none;
  }

  .username {
    display: none;
  }
}
</style>
