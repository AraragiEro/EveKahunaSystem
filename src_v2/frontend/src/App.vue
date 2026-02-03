<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { ArrowDown, Document } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useHelpStore } from '@/stores/help'
import { useEdition } from '@/composables/useEdition'
import smallSideBar from './components/sideBar/smallSideBar.vue'
import HelpDrawer from './components/HelpDrawer.vue'
import VipPricingDialog from './components/VipPricingDialog.vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import githubIcon from '@/assets/github-mark.svg'
import aifadianLogo from '@/assets/横版-白底-透明背景.png'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const helpStore = useHelpStore()
const { isEnterprise } = useEdition()

// GitHub 仓库地址
const GITHUB_REPO_URL = 'https://github.com/AraragiEro/EveKahunaSystem.git'

// 打开 GitHub 仓库
const openGitHub = () => {
  window.open(GITHUB_REPO_URL, '_blank')
}

// 捐赠链接（从环境变量读取）
const donateLink = computed(() => import.meta.env.VITE_DONATE_LINK as string | undefined)
const showDonateButton = computed(() => !!donateLink.value)

// 打开捐赠链接
const openDonate = () => {
  if (donateLink.value) {
    window.open(donateLink.value, '_blank')
  }
}

// 全局快捷键支持（F1 打开文档）
const handleKeyDown = (event: KeyboardEvent) => {
  // F1 键打开文档
  if (event.key === 'F1') {
    event.preventDefault()
    helpStore.openHelp()
  }
  // Ctrl+H 或 Cmd+H 打开文档
  if ((event.ctrlKey || event.metaKey) && event.key === 'h') {
    event.preventDefault()
    helpStore.openHelp()
  }
}


// 定义公开页面列表（不需要认证和主布局）
const publicPages = ['login', 'landing', 'forbidden', 'characterAuthClose', 'publicStorage', 'allianceContract']
const isPublicPage = computed(() => publicPages.includes(route.name as string))

// 主菜单配置 - 使用 computed 响应式地生成菜单项
const menuItems = computed(() => {
  const items: { id: number; icon: string; label: string; active: boolean; route: string }[] = []
  let id_index = 1

  // 首页始终显示
  items.push({ id: id_index++, icon: 'Tickets', label: 'TODO', active: router.currentRoute.value.path === '/todolist' || router.currentRoute.value.path === '/', route: '/todolist' })
  if (authStore.user?.roles.includes('vip_alpha') || authStore.user?.roles.includes('vip_omega')) {
    items.push({ id: id_index++, icon: 'House', label: '总览', active: router.currentRoute.value.path.startsWith('/home'), route: '/home' })
  }

  // 根据用户角色动态添加菜单项
  const userRoles = authStore.user?.roles || []
  if (userRoles.includes('user')) {
    items.push({ id: id_index++, icon: 'Cpu', label: '工业', active: router.currentRoute.value.path.startsWith('/industry'), route: '/industry' })
    // items.push({ id: id_index++, icon: 'ShoppingBag', label: '公司商城', active: router.currentRoute.value.path === '/corpShop', route: '/corpShop' })
  }

  // 企业版专用菜单项
  if (isEnterprise) {
    if (userRoles.includes('vip_omega')) {
      items.push({
        id: id_index++,
        icon: 'PieChart',
        label: '市场分析',
        active: router.currentRoute.value.path.startsWith('/market'),
        route: '/market'
      })
    }
  }

  if (userRoles.includes('user')) {
    items.push({ id: id_index++, icon: 'Opportunity', label: '实用工具', active: router.currentRoute.value.path === '/utils', route: '/utils' })
    items.push({ id: id_index++, icon: 'ChatLineRound', label: '留言板', active: router.currentRoute.value.path === '/messageBoard', route: '/messageBoard' })
    items.push({ id: id_index++, icon: 'Setting', label: '设置', active: router.currentRoute.value.path.startsWith('/setting'), route: '/setting' })
  }

  if (userRoles.includes('admin')) {
    items.push({ id: id_index++, icon: 'Cpu', label: '管理员', active: router.currentRoute.value.path.startsWith('/admin'), route: '/admin' })
  }

  return items
})

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}

// 订阅状态计算属性
const hasAlphaSubscription = computed(() => {
  const userRoles = authStore.user?.roles || []
  return userRoles.includes('vip_alpha')
})

const hasOmegaSubscription = computed(() => {
  const userRoles = authStore.user?.roles || []
  return userRoles.includes('vip_omega')
})

// 判断是否为非VIP用户
const isNonVip = computed(() => {
  return !hasAlphaSubscription.value && !hasOmegaSubscription.value
})

// VIP弹窗控制
const vipDialogVisible = ref(false)

// 打开VIP弹窗
const openVipDialog = () => {
  vipDialogVisible.value = true
}

// 当前时间，用于定时更新剩余时间显示
const currentTime = ref(Date.now())

// 获取订阅有效期
const subscriptionEndDate = computed(() => {
  return authStore.user?.vipEndDate || null
})

// 检查是否过期
const isExpired = (endDateStr: string | null | undefined): boolean => {
  if (!endDateStr) return true

  try {
    const endDate = new Date(endDateStr)
    const now = new Date(currentTime.value)
    return endDate.getTime() <= now.getTime()
  } catch {
    return true
  }
}

// 计算剩余时间文本
const getRemainingTimeText = (endDateStr: string | null | undefined): string => {
  if (!endDateStr) return ''

  try {
    const endDate = new Date(endDateStr)
    const now = new Date(currentTime.value)
    const diff = endDate.getTime() - now.getTime()

    if (diff <= 0) {
      return ''
    }

    const days = Math.floor(diff / (1000 * 60 * 60 * 24))
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))

    if (days > 0) {
      return `剩余${days}天${hours}小时`
    } else if (hours > 0) {
      return `剩余${hours}小时${minutes}分钟`
    } else {
      return `剩余${minutes}分钟`
    }
  } catch {
    return ''
  }
}

// 获取剩余时间标签类型（颜色）
const getRemainingTimeTagType = (endDateStr: string | null | undefined): string => {
  if (!endDateStr) return 'info'

  try {
    const endDate = new Date(endDateStr)
    const now = new Date(currentTime.value)
    const diff = endDate.getTime() - now.getTime()

    if (diff <= 0) {
      return 'danger'
    }

    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days < 1) {
      return 'danger' // 少于1天显示危险色
    } else if (days < 7) {
      return 'warning' // 少于7天显示警告色
    } else {
      return 'success' // 7天以上显示成功色
    }
  } catch {
    return 'info'
  }
}

// 定时更新当前时间（每分钟更新一次）
let timeUpdateInterval: number | null = null

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  // 每分钟更新一次当前时间
  timeUpdateInterval = window.setInterval(() => {
    currentTime.value = Date.now()
  }, 60000) // 60000ms = 1分钟
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
    <!-- 公开页面（登录页、403页面等）不显示主布局 -->
    <router-view v-if="isPublicPage" />

    <!-- 主应用布局 - 确保用户信息已加载 -->
    <el-container v-else-if="authStore.isAuthenticated">
      <!-- 左侧窄侧边菜单 -->
      <smallSideBar :menu-items="menuItems" />

      <!-- 主内容区域 -->
      <el-container class="main-container">
        <el-header class="main-header">
          <div class="header-content">
            <div class="header-title">
              <h2>Kahuna-System V1.5.1</h2>
              <el-tag :type="isEnterprise ? 'success' : 'info'" size="small" class="edition-tag">
                {{ isEnterprise ? '紫竹梅特供版' : '社区版' }}
              </el-tag>
              <el-tag v-if="hasAlphaSubscription && !hasOmegaSubscription" type="warning" size="small"
                class="edition-tag">
                Alpha订阅
              </el-tag>
              <el-tag
                v-if="hasAlphaSubscription && !hasOmegaSubscription && subscriptionEndDate && !isExpired(subscriptionEndDate)"
                :type="getRemainingTimeTagType(subscriptionEndDate)" size="small" class="edition-tag">
                {{ getRemainingTimeText(subscriptionEndDate) }}
              </el-tag>
              <el-tag v-if="hasOmegaSubscription" type="danger" size="small" class="edition-tag">
                Omega订阅
              </el-tag>
              <el-tag v-if="hasOmegaSubscription && subscriptionEndDate && !isExpired(subscriptionEndDate)"
                :type="getRemainingTimeTagType(subscriptionEndDate)" size="small" class="edition-tag">
                {{ getRemainingTimeText(subscriptionEndDate) }}
              </el-tag>
              <el-button
                v-if="isNonVip"
                type="primary"
                size="small"
                @click="openVipDialog"
                class="edition-tag get-vip-button"
              >
                获取VIP
              </el-button>
            </div>

            <div class="header-actions">

              <!-- 捐赠按钮 -->
              <el-button v-if="showDonateButton" @click="openDonate" title="支持作者"
                class="header-action-btn donate-button">
                <img :src="aifadianLogo" alt="爱发电" class="donate-icon" />
              </el-button>

              <!-- GitHub 按钮 -->
              <el-button @click="openGitHub" title="打开 GitHub 仓库" class="header-action-btn github-btn">
                <img :src="githubIcon" alt="GitHub" class="github-icon" />
                <span class="btn-label">仓库</span>
              </el-button>

              <!-- 文档按钮 -->
              <el-button @click="helpStore.openHelp" title="打开使用说明 (F1)" class="header-action-btn">
                <el-icon>
                  <Document />
                </el-icon>
                <span class="btn-label">指南</span>
              </el-button>

              <!-- 用户信息和退出按钮 -->
              <div class="user-info">
                <el-dropdown @command="handleLogout">
                  <span class="user-dropdown">
                    <el-avatar :size="32">
                      {{ authStore.user?.username?.charAt(0)?.toUpperCase() }}
                    </el-avatar>
                    <span class="username">{{ authStore.user?.username }}</span>
                    <el-icon>
                      <ArrowDown />
                    </el-icon>
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
          <div class="main-content-inner">
            <router-view />
          </div>
        </el-main>

        <el-footer class="main-footer">
          <span>© 2025 Kahuna Kahuna-System. 紫竹梅重工.</span>
        </el-footer>
      </el-container>
    </el-container>

    <!-- 全局文档 Drawer -->
    <HelpDrawer />

    <!-- VIP方案弹窗 -->
    <VipPricingDialog v-model="vipDialogVisible" />
  </div>
</template>

<style scoped>
.main-container {
  margin-left: 60px;
  transition: margin-left 0.3s ease;
  min-height: 98vh;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.kahuna-container {
  height: 100%;
  background-color: #f5f7fa;
  overflow: hidden;
}

/* 主内容区域样式 */
.main-header {
  background: white;
  border-bottom: 1px solid #e1e8ed;
  padding: 0 24px;
  display: flex;
  align-items: center;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  border-top-left-radius: 12px;
  border-top-right-radius: 12px;
  flex-shrink: 0;
  height: 64px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-content h2 {
  margin: 0;
  color: #2c3e50;
  font-weight: 600;
  font-size: 20px;
}

.edition-tag {
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 4px;
}

.get-vip-button {
  margin-left: 8px;
  font-size: 12px;
  padding: 4px 12px;
  height: auto;
  line-height: 1.5;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.main-content {
  flex: 1;
  padding: 24px;
  background: #f5f7fa;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.main-content-inner {
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.content-wrapper {
  background: white;
  border-radius: 12px;
  padding: 32px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  height: 100%;
  overflow: auto;
}

.content-wrapper h3 {
  margin: 0 0 16px 0;
  color: #2c3e50;
  font-weight: 600;
}

.content-wrapper p {
  margin: 0;
  color: #64748b;
  line-height: 1.6;
}

.main-footer {
  background: white;
  border-top: 1px solid #e1e8ed;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  font-size: 14px;
  height: 60px;
  flex-shrink: 0;
}

/* 优化 el-main 的默认样式 */
:deep(.el-main) {
  padding: 0;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .sidebar {
    width: 60px !important;
  }

  .menu-item {
    width: 50px;
    height: 50px;
  }

  .main-header {
    padding: 0 16px;
    height: 56px;
  }

  .header-content h2 {
    font-size: 18px;
  }

  .main-content {
    padding: 16px;
  }

  .main-footer {
    height: 48px;
    font-size: 12px;
  }
}

.user-info {
  margin-left: 16px;
}

.user-dropdown {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background-color 0.2s;
}

.user-dropdown:hover {
  background-color: #f1f5f9;
}

.username {
  color: #64748b;
  font-size: 14px;
}

.header-action-btn {
  border: 1px solid #e1e8ed;
  background: #ffffff;
  color: #64748b;
  transition: all 0.2s;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  border-radius: 8px;
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.header-action-btn:hover {
  background-color: #f8fafc;
  border-color: #cbd5e1;
  color: #2c3e50;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  transform: translateY(-1px);
}

.header-action-btn:active {
  transform: translateY(0);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.github-btn {
  padding: 8px 16px;
}

.github-icon {
  width: 18px;
  height: 18px;
  display: block;
  opacity: 0.8;
  transition: opacity 0.2s;
  flex-shrink: 0;
}

.github-btn:hover .github-icon {
  opacity: 1;
}

.btn-label {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}

.donate-icon {
  height: 50px;
  width: auto;
  object-fit: contain;
  display: block;
  flex-shrink: 0;
}

.header-action-btn :deep(.el-icon) {
  font-size: 18px;
  flex-shrink: 0;
}

/* 优化主内容区域的滚动条样式 */
.main-content-inner {
  scrollbar-width: thin;
  scrollbar-color: #c1c1c1 #f1f1f1;
}

.main-content-inner::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.main-content-inner::-webkit-scrollbar-track {
  background: #f5f7fa;
  border-radius: 4px;
}

.main-content-inner::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.main-content-inner::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>
