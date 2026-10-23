<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { http } from '@/http'
import {
  ArrowDown,
  ChatLineRound,
  Cpu,
  DataAnalysis,
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
import PageContainer from './components/layout/PageContainer.vue'
import AppFooter from './components/AppFooter.vue'
import HelpDrawer from './components/HelpDrawer.vue'
import RouteProgressBar from './components/global/RouteProgressBar.vue'
import VipPricingDialog from './components/VipPricingDialog.vue'
import githubIcon from '@/assets/github-mark.svg'
// 爱发电：只取官方标里的方形图标。原来的 464×240 横版字标压到 24px 高时，
// 图标和字标各只剩约 12px，细节全糊；文字改由页面字体渲染，与「仓库」「指南」按钮一致。
import aifadianIcon from '@/assets/afdian-icon.png'
import { GITHUB_REPO_URL, SITE_NAME_EN, APP_VERSION } from '@/config/site'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const helpStore = useHelpStore()
const themeStore = useThemeStore()
const { isEnterprise } = useEdition()

const publicPages = ['login', 'landing', 'announcements', 'forbidden', 'notFound', 'characterAuthClose', 'publicStorage', 'publicWorkflow', 'allianceContract', 'priceEstimator', 'piProfit']
const headerTitle = `${SITE_NAME_EN} ${APP_VERSION}`

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
  | typeof DataAnalysis
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
    icon: DataAnalysis,
    label: '仪表盘',
    active: currentPath === '/dashboard' || currentPath === '/',
    route: '/dashboard',
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

const handleLogout = async () => {
  try {
    await http.post('/auth/logout')
  } catch {
    // 即使后端注销失败也清除前端状态
  }
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

onMounted(async () => {
  // 应用启动时从 httpOnly cookie 恢复认证状态
  // 避免页面刷新后 Pinia store 被清空导致 isAuthenticated 误判
  await authStore.checkAuth()
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
    <RouteProgressBar />
    <div v-if="isPublicPage" class="public-page-scroll">
      <router-view />
    </div>

    <el-container v-else-if="authStore.isAuthenticated" class="app-shell">
      <smallSideBar :menu-items="menuItems" />

      <el-container class="main-container">
        <el-header class="main-header">
          <PageContainer class="header-content" flush>
            <div class="header-title">
              <h2>{{ headerTitle }}</h2>
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
                <img :src="aifadianIcon" alt="爱发电" class="donate-icon" />
                <span class="btn-label">爱发电</span>
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
          </PageContainer>
        </el-header>

        <el-main class="main-content">
          <PageContainer class="main-page" fill flush>
            <div class="main-scroll">
              <router-view />
            </div>
          </PageContainer>
        </el-main>

        <AppFooter variant="compact" />
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
  /* 图标轨宽度进入版心居中公式：PageContainer 会扣掉半个 --k-rail-w。
     这里只按**收起态**的 60px 让位；hover 展开是浮层覆盖（P2-e），
     内容区宽度不随之变化，所以不要再写 transition: margin-left。 */
  margin-left: var(--k-rail-w, 60px);
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: transparent;
}

/* 注：图标轨 hover 展开（60 → 148px）是**浮层覆盖**，不再改内容区的 margin-left。
   P1-C2 曾在这里把展开宽度计入居中公式，代价是展开瞬间内容区窄 88px、表格列宽重算；
   P2-e 按「浮层覆盖，内容不动」改回固定 60px。想再加回来先看 PageContainer 的注释。 */

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

/* .header-title[data-v] .edition-tag 的权重 (0,3,0) 已经压过 EP 的
   .el-tag.el-tag--success (0,2,0)，spec 上不需要 !important。 */
.header-title :deep(.edition-tag) {
  background: var(--k-color-surface-soft);
  color: var(--k-color-text-secondary);
  border-color: var(--k-color-border);
}

.header-title :deep(.edition-tag.el-tag--success) {
  background: color-mix(in srgb, var(--k-color-success) 16%, var(--k-color-surface-soft));
  color: var(--k-color-success);
}

.header-title :deep(.edition-tag.el-tag--warning) {
  background: color-mix(in srgb, var(--k-color-warning) 16%, var(--k-color-surface-soft));
  color: var(--k-color-warning);
}

.header-title :deep(.edition-tag.el-tag--danger) {
  background: color-mix(in srgb, var(--k-color-danger) 16%, var(--k-color-surface-soft));
  color: var(--k-color-danger);
}

.header-title :deep(.edition-tag.el-tag--info) {
  background: color-mix(in srgb, var(--k-color-primary) 10%, var(--k-color-surface-soft));
  color: var(--k-color-primary);
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
  width: 16px;
  height: 16px;
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

.global-theme-switch {
  position: fixed;
  right: 14px;
  /* 抬到页脚之上，避免悬浮按钮压住页脚右下角的版权/协议文字 */
  bottom: 62px;
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
  /* 窄屏不再需要给展开态预留 148px：轨道是浮层，内容区始终只让位 60px（见 .main-container） */
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

/* ── P2-C ≤640：页头不要吃掉半个屏幕 ─────────────────────────────────
   375 下页头实测 ~200px（标题两行 + 3 个标签 + 4 个动作按钮竖排），
   内容区只剩 400px。这里只压缩留白与字号，不隐藏任何信息
   （版本/订阅标签、动作按钮全部保留），1280 及以上不受影响。 */
@media (max-width: 640px) {
  .main-header {
    min-height: 0;
    padding: 8px 10px;
  }

  .main-content {
    padding: 8px;
  }

  .header-title h2 {
    font-size: 17px;
  }

  .header-title {
    gap: 6px;
  }

  .header-actions {
    gap: 6px;
  }

  .header-action-btn {
    padding: 5px 8px;
  }
}
</style>

<!-- ─────────────────────────────────────────────────────────────────────
     全局 Element Plus 桥接（P1-C3）：独立的非 scoped style 块，必须放在
     scoped 块之后。三个原因：
       1. EP 的 message / message-box / notification / dialog 都 teleport 到
          body，scoped 选择器根本选不到；
       2. :global() 在 scoped 块里会丢类选择器（见 kahuna-lessons 深色模式）；
       3. 要压过 element-plus/dist/index.css 的默认值，只能靠「后导入 + 同权重」，
          App.vue 在 main.ts 里晚于 theme.css 求值。
     本块只补 theme.css 的缺口，不重复它已有的规则：
       · EP 派生色（*-light-N / *-dark-2）按 --k-* 品牌色重算；
       · message / message-box / notification / alert / skeleton / switch /
         checkbox 六个组件此前 0 选择器，深色下是白底或浅灰底。
     ───────────────────────────────────────────────────────────────────── -->
<style>
/* ── 1. 派生色：EP 的浅底/浅描边全靠 light-N ──────────────────────────────
   EP 默认的 light-N 是按它自己的蓝色算出来的（比品牌蓝更浅的几个 EP 固定档），浅色下
   tag、plain 按钮、message、alert 会整片发蓝。深色那边 theme.css 已按品牌色
   重算过 primary，这里只补浅色 primary，避免覆盖已有的深色观感。 */
:root {
  --el-color-primary-light-3: color-mix(in srgb, var(--k-color-primary) 70%, var(--k-color-tint));
  --el-color-primary-light-5: color-mix(in srgb, var(--k-color-primary) 50%, var(--k-color-tint));
  --el-color-primary-light-7: color-mix(in srgb, var(--k-color-primary) 30%, var(--k-color-tint));
  --el-color-primary-light-8: color-mix(in srgb, var(--k-color-primary) 20%, var(--k-color-tint));
  --el-color-primary-light-9: color-mix(in srgb, var(--k-color-primary) 10%, var(--k-color-tint));
  --el-color-primary-dark-2: color-mix(in srgb, var(--k-color-primary) 80%, var(--k-color-shade));
}

/* success / warning / danger / error / info 的派生色：EP 里 danger 与 error 是两套
   变量名（部分组件只读 --el-color-error），必须一起桥。混合基色取
   --k-color-surface，浅色得到浅底、深色得到暗底，一条声明同时成立，不必再写
   [data-theme] 分支。info 没有品牌色，用次级文字色承担「中性提示」。 */
:root,
html[data-theme='dark'] {
  --el-color-info: var(--k-color-text-secondary);

  --el-color-success-light-3: color-mix(in srgb, var(--k-color-success) 70%, var(--k-color-surface));
  --el-color-success-light-5: color-mix(in srgb, var(--k-color-success) 50%, var(--k-color-surface));
  --el-color-success-light-7: var(--k-color-success-soft-border);
  --el-color-success-light-8: color-mix(in srgb, var(--k-color-success) 20%, var(--k-color-surface));
  --el-color-success-light-9: var(--k-color-success-soft);
  --el-color-success-dark-2: color-mix(in srgb, var(--k-color-success) 80%, var(--k-color-shade));

  --el-color-warning-light-3: color-mix(in srgb, var(--k-color-warning) 70%, var(--k-color-surface));
  --el-color-warning-light-5: color-mix(in srgb, var(--k-color-warning) 50%, var(--k-color-surface));
  --el-color-warning-light-7: var(--k-color-warning-soft-border);
  --el-color-warning-light-8: color-mix(in srgb, var(--k-color-warning) 20%, var(--k-color-surface));
  --el-color-warning-light-9: var(--k-color-warning-soft);
  --el-color-warning-dark-2: color-mix(in srgb, var(--k-color-warning) 80%, var(--k-color-shade));

  --el-color-danger-light-3: color-mix(in srgb, var(--k-color-danger) 70%, var(--k-color-surface));
  --el-color-danger-light-5: color-mix(in srgb, var(--k-color-danger) 50%, var(--k-color-surface));
  --el-color-danger-light-7: var(--k-color-danger-soft-border);
  --el-color-danger-light-8: color-mix(in srgb, var(--k-color-danger) 20%, var(--k-color-surface));
  --el-color-danger-light-9: var(--k-color-danger-soft);
  --el-color-danger-dark-2: color-mix(in srgb, var(--k-color-danger) 80%, var(--k-color-shade));

  --el-color-error-light-3: color-mix(in srgb, var(--k-color-danger) 70%, var(--k-color-surface));
  --el-color-error-light-5: color-mix(in srgb, var(--k-color-danger) 50%, var(--k-color-surface));
  --el-color-error-light-7: var(--k-color-danger-soft-border);
  --el-color-error-light-8: color-mix(in srgb, var(--k-color-danger) 20%, var(--k-color-surface));
  --el-color-error-light-9: var(--k-color-danger-soft);
  --el-color-error-dark-2: color-mix(in srgb, var(--k-color-danger) 80%, var(--k-color-shade));

  --el-color-info-light-3: color-mix(in srgb, var(--k-color-text-secondary) 70%, var(--k-color-surface));
  --el-color-info-light-5: color-mix(in srgb, var(--k-color-text-secondary) 50%, var(--k-color-surface));
  --el-color-info-light-7: color-mix(in srgb, var(--k-color-text-secondary) 30%, var(--k-color-surface));
  --el-color-info-light-8: color-mix(in srgb, var(--k-color-text-secondary) 20%, var(--k-color-surface));
  --el-color-info-light-9: color-mix(in srgb, var(--k-color-text-secondary) 12%, var(--k-color-surface));

  /* 浮层/分割线：EP 深色默认是近黑（比本项目 surface 更黑一档）与中性灰描边，与本项目紫色系不搭；
     浅色默认是纯白浮层与浅灰分割线。 */
  --el-bg-color-overlay: var(--k-color-surface);
  --el-border-color-lighter: var(--k-color-border-subtle);
  --el-fill-color-darker: var(--k-color-surface-strong);
}

/* ── 2. message（716 处 ElMessage 调用，最高频） ─────────────────────────
   深色下的浅底来自 --el-color-info-light-9（EP 深色变量在 html.dark 上才生效，
   本项目同时挂了 data-theme，两条路径都要能兜住，派生色已在上面统一桥接）。 */
.el-message {
  --el-message-border-color: var(--k-color-border-subtle);
  box-shadow: var(--k-shadow-sm);
}

.el-message.is-plain {
  background-color: var(--k-color-surface);
  border-color: var(--k-color-border);
}

.el-message__content {
  color: var(--k-color-text);
}

.el-message .el-message__closeBtn {
  color: var(--k-color-text-secondary);
}

.el-message .el-message__closeBtn:hover {
  color: var(--k-color-text);
}

/* ── 3. message-box（68 处 ElMessageBox，删除确认等） ────────────────────
   EP 这里读 --el-bg-color（已桥接），但标题/正文/关闭按钮仍是 EP 的灰阶，
   深色下正文是 EP 的中灰（压在深色 card 上勉强能看）、关闭按钮几乎看不见。 */
.el-message-box {
  background-color: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  box-shadow: var(--k-shadow-md);
}

.el-message-box__title {
  color: var(--k-color-text);
}

.el-message-box__content {
  color: var(--k-color-text-secondary);
}

.el-message-box__headerbtn .el-message-box__close {
  color: var(--k-color-text-secondary);
}

.el-message-box__headerbtn:hover .el-message-box__close,
.el-message-box__headerbtn:focus .el-message-box__close {
  color: var(--k-color-primary);
}

/* 删除确认里写死的内联告警色（模板里 style="color:#e6a23c"，scoped/变量都够不到） */
.el-message-box [style*='color: #e6a23c'],
.el-message-box [style*='color:#e6a23c'] {
  color: var(--k-color-warning) !important;
}

/* ── 4. notification（深色下 EP 用 --el-bg-color-overlay 的近黑底） ─────── */
.el-notification {
  background-color: var(--k-color-surface);
  border-color: var(--k-color-border);
  box-shadow: var(--k-shadow-md);
}

.el-notification__title {
  color: var(--k-color-text);
}

.el-notification__content {
  color: var(--k-color-text-secondary);
}

.el-notification .el-notification__closeBtn {
  color: var(--k-color-text-secondary);
}

/* ── 5. alert（基础规则写死 background:var(--el-color-white)，无 type 时纯白） */
.el-alert:not([class*='el-alert--']) {
  background-color: var(--k-color-surface-soft);
  color: var(--k-color-text);
}

.el-alert.is-light .el-alert__close-btn {
  color: var(--k-color-text-secondary);
}

.el-alert.is-light .el-alert__close-btn:hover {
  color: var(--k-color-text);
}

/* ── 6. skeleton（骨架色取自 --el-fill-color，浅色是 EP 自带的浅灰） ────── */
.el-skeleton {
  --el-skeleton-color: var(--k-color-surface-soft);
  --el-skeleton-to-color: var(--k-color-surface-strong);
}

.el-skeleton__first-line,
.el-skeleton__paragraph {
  background: var(--k-color-surface-soft);
}

/* ── 7. switch（off 轨道默认取 --el-border-color，未选中态偏白） ─────────── */
.el-switch {
  --el-switch-on-color: var(--k-color-primary);
  --el-switch-off-color: color-mix(in srgb, var(--k-color-border) 76%, var(--k-color-surface));
}

.el-switch__label {
  color: var(--k-color-text);
}

.el-switch__label.is-active {
  color: var(--k-color-primary);
}

.el-switch__core .el-switch__action {
  background-color: var(--k-color-text-inverse);
}

/* ── 8. checkbox（勾选框底取 --el-fill-color-blank，深色下会漏成透明/白） ── */
.el-checkbox {
  --el-checkbox-text-color: var(--k-color-text-secondary);
  --el-checkbox-bg-color: var(--k-color-surface);
  --el-checkbox-input-border: 1px solid var(--k-color-border);
}

.el-checkbox__label {
  color: var(--k-color-text);
}

.el-checkbox__inner {
  background-color: var(--k-color-surface);
  border-color: var(--k-color-border);
}

.el-checkbox__input.is-checked .el-checkbox__inner,
.el-checkbox__input.is-indeterminate .el-checkbox__inner {
  background-color: var(--k-color-primary);
  border-color: var(--k-color-primary);
}

.el-checkbox__input.is-checked .el-checkbox__inner::after {
  border-color: var(--k-color-text-inverse);
}

.el-checkbox__input.is-checked + .el-checkbox__label {
  color: var(--k-color-text);
}

.el-checkbox.is-bordered {
  border-color: var(--k-color-border);
}

.el-checkbox__input.is-disabled .el-checkbox__inner {
  background-color: var(--k-color-surface-soft);
  border-color: var(--k-color-border-subtle);
}

.el-checkbox__input.is-disabled + span.el-checkbox__label {
  color: var(--k-color-text-secondary);
  opacity: 0.6;
}

/* ── 9. 模板内联颜色的兜底救援 ────────────────────────────────────────────
   有些颜色写在 template 的 :label-style / style 里（P1-C3 只改 style 块，
   不动 template），内联样式必须用 !important 才压得住。theme.css 已对
   dialog / drawer 做过同类救援，这里补 descriptions 与 message-box。 */
.el-descriptions [style*='color: #606266'],
.el-descriptions [style*='color:#606266'] {
  color: var(--k-color-text-secondary) !important;
}

.el-descriptions [style*='color: #303133'],
.el-descriptions [style*='color:#303133'] {
  color: var(--k-color-text) !important;
}

/* ── 10. effect="dark" 的实底标签：白字压在亮绿/亮橙上只有 2.2~2.3:1 ──────
   EP 的 dark effect 直接 `color: var(--el-color-white)` 铺在语义色上；
   本项目的 success/warning 在深色下是亮绿/亮橙，白字几乎糊成一片。
   深色下改成「同色系暗底 + 语义色文字」，与全站其他标签观感一致。
   primary / danger 的白字对比度本身够（3.8:1 以上），不动。 */
html[data-theme='dark'] .el-tag--success.el-tag--dark {
  background-color: color-mix(in srgb, var(--k-color-success) 20%, var(--k-color-surface));
  border-color: color-mix(in srgb, var(--k-color-success) 38%, var(--k-color-surface));
  color: var(--k-color-success);
}

html[data-theme='dark'] .el-tag--warning.el-tag--dark {
  background-color: color-mix(in srgb, var(--k-color-warning) 20%, var(--k-color-surface));
  border-color: color-mix(in srgb, var(--k-color-warning) 38%, var(--k-color-surface));
  color: var(--k-color-warning);
}

/* ── 11. dev-only：Vue DevTools 浮层不要压住页脚 ───────────────────────────
   vite-plugin-vue-devtools 在开发模式下会挂一个 fixed 浮层，默认贴着视口底部
   24px、水平居中——1440×900 下正好盖在页脚中间的「QQ群 979335885」上。
   它自己用内联 top/left 定位（top = 视口高 - 24），所以只能用 !important 顶上去。
   只命中它自己的类名，生产构建里没有这个节点，不会影响真实页面。 */
.vue-devtools__anchor {
  /* 72px = 页脚 48px + 浮层自身约 30px/2 的余量，保证 pill 整体落在页脚上方 */
  top: calc(100vh - 72px) !important;
}
</style>
