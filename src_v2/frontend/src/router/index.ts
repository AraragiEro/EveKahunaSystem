import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { setupAuthGuards } from './guards'
import { registerRouteProgress } from '@/composables/useRouteProgress'

// 条件加载企业版路由
// 社区版（开源同步）会删除 src/router/enterprise.ts，
// 所以用 import.meta.glob 可选加载：模块不存在时得到空对象，
// 不会产生 rollup 无法解析的静态导入路径，社区版也能正常构建。
const APP_EDITION = (import.meta.env.VITE_APP_EDITION as string) || 'community'

type EnterpriseRouteModule = {
  getEnterpriseRoutes?: (edition: string) => RouteRecordRaw[]
}

const enterpriseRouteModules = import.meta.glob('./enterprise.ts', { eager: true }) as Record<
  string,
  EnterpriseRouteModule
>

/**
 * 解析企业版路由
 * 仅当 APP_EDITION === 'enterprise' 且企业版路由模块存在时才加载，否则返回空数组
 * @param edition 应用版本 ('enterprise' | 'community')
 */
function resolveEnterpriseRoutes(edition: string): RouteRecordRaw[] {
  if (edition !== 'enterprise') {
    return []
  }
  const enterpriseModule = enterpriseRouteModules['./enterprise.ts']
  if (!enterpriseModule || typeof enterpriseModule.getEnterpriseRoutes !== 'function') {
    // 企业版路由模块不存在（社区版/裁剪版）时静默跳过
    console.warn('[路由] 未找到企业版路由模块，已跳过企业版路由')
    return []
  }
  try {
    return enterpriseModule.getEnterpriseRoutes(edition)
  } catch (error) {
    console.warn('[路由] 企业版路由加载失败:', error)
    return []
  }
}

// 定义基础路由
const baseRoutes = [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/landing',
      name: 'landing',
      component: () => import('../views/LandingPage.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/announcements',
      name: 'announcements',
      component: () => import('../views/announcements/AnnouncementView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/',
      redirect: '/landing'
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('../views/DashboardView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/todolist',
      redirect: '/dashboard'
    },
    {
      path: '/home',
      name: 'home',
      component: () => import('../views/HomeView.vue'),
      meta: { requiresAuth: true , roles: ['vip_alpha', 'vip_omega'] },
      redirect: '/home/overview',
      children: [
        {
          path: 'overview',
          name: 'homeOverview',
          component: () => import('../views/home/overview.vue'),
        },
        {
          path: 'history',
          name: 'homeHistory',
          component: () => import('../views/home/history.vue'),
        },
        {
          path: 'orderStats',
          name: 'homeOrderStats',
          component: () => import('../views/home/orderStats.vue'),
        },
      ],
    },
    {
      path: '/setting',
      name: 'setting',
      component: () => import('../views/settingView.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'user'] },
      children: [
        {
          path: 'characterSetting',
          name: 'userSetting',
          component: () => import('../views/setting/characterSetting.vue'),
          meta: { requiresAuth: true, roles: ['user'] }
        },
        {
          path: 'industrySetting',
          name: 'industrySetting',
          component: () => import('../views/setting/industrySetting.vue'),
          meta: { requiresAuth: true, roles: ['admin', 'user'] }
        },
        {
          path: 'accountSetting',
          name: 'accountSetting',
          component: () => import('../views/setting/accountSetting.vue'),
          meta: { requiresAuth: true, roles: ['user'] }
        },
      ],
    },
    {
      path: '/industry',
      name: 'industry',
      redirect: '/industry/industryPlan',
      component: () => import('../views/industryView.vue'),
      children: [
        {
          path: 'overview',
          name: 'overview',
          component: () => import('../views/industry/overview.vue'),
        },
        {
          path: 'assetView',
          name: 'assetView',
          component: () => import('../views/industry/assetView.vue'),
          meta: { requiresAuth: true, roles: ['vip_alpha'] },
        },
        {
          path: 'industryPlan',
          name: 'industryPlan',
          component: () => import('../views/industry/industryPlan.vue'),
        },
        {
          path: 'flowDecomposition',
          name: 'flowDecomposition',
          component: () => import('../views/industry/flowDecomposition.vue'),
        },
        {
          path: 'workflow',
          name: 'workflow',
          component: () => import('../views/industry/workflow.vue'),
        },
        {
          path: 'testPage',
          name: 'testPage',
          component: () => import('../views/industry/testPage.vue'),
        },
      ],
    },
    {
      path: '/utils/piProfit',
      name: 'piProfit',
      component: () => import('../views/industry/piProfit.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/corpShop',
      name: 'corpShop',
      component: () => import('../views/corpShop.vue'),
    },
    {
      path: '/utils',
      name: 'utils',
      component: () => import('../views/utilsView.vue'),
    },
    {
      path: '/utils/estimator',
      name: 'priceEstimator',
      component: () => import('../views/PriceEstimatorView.vue'),
    },
    {
      path: '/messageBoard',
      name: 'messageBoard',
      component: () => import('../views/messageBoardView.vue'),
      meta: { requiresAuth: true, roles: ['user'] }
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('../views/adminView.vue'),
      children: [
        {
          path: 'userManagement',
          name: 'userManagement',
          component: () => import('../views/admin/userManagement.vue'),
        },
        {
          path: 'permissionManagement',
          name: 'permissionManagement',
          component: () => import('../views/admin/permissionManagement.vue'),
        },
        {
          path: 'inviteCodeManagement',
          name: 'inviteCodeManagement',
          component: () => import('../views/admin/inviteCodeManagement.vue'),
        },
        {
          path: 'vipManagement',
          name: 'vipManagement',
          component: () => import('../views/admin/vipManagement.vue'),
        },
        {
          path: 'websiteDataStatistics',
          name: 'websiteDataStatistics',
          component: () => import('../views/admin/websiteDataStatistics.vue'),
        },
        {
          path: 'websiteManagement',
          name: 'websiteManagement',
          component: () => import('../views/admin/websiteManagement.vue'),
        },
        {
          path: 'esiModuleStatus',
          name: 'esiModuleStatus',
          component: () => import('../views/admin/esiModuleStatus.vue'),
        },
      ],
    },
    {
      path: '/forbidden',
      name: 'forbidden',
      component: () => import('../views/ForbiddenView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/storage/:sid',
      name: 'publicStorage',
      component: () => import('../views/public/storage.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/workflow/:token',
      name: 'publicWorkflow',
      component: () => import('../views/public/workflow.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/setting/characterSetting/auth/close',
      name: 'characterAuthClose',
      component: () => import('../views/setting/characterAuthClose.vue'),
      meta: { requiresAuth: false }
    }
]

// 条件添加企业版路由
const routes: RouteRecordRaw[] = [...baseRoutes, ...resolveEnterpriseRoutes(APP_EDITION)]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// 注册路由切换进度条（必须早于认证守卫，否则要等认证通过才会显示）
registerRouteProgress(router)

// 设置认证守卫
setupAuthGuards(router)

export default router
