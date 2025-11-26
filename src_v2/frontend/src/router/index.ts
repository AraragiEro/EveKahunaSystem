import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { setupAuthGuards } from './guards'
import HomeView from '../views/HomeView.vue'

// 条件加载企业版路由
// 使用动态导入，避免顶层 await，使用懒加载方式
const APP_EDITION = (import.meta.env.VITE_APP_EDITION as string) || 'community'

// 定义基础路由
const baseRoutes = [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/',
      redirect: '/home'
    },
    {
      path: '/home',
      name: 'home',
      component: HomeView,
      meta: { requiresAuth: true }
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
      path: '/setting/characterSetting/auth/close',
      name: 'characterAuthClose',
      component: () => import('../views/setting/characterAuthClose.vue'),
      meta: { requiresAuth: false }
    }
]

// 条件添加企业版路由
const routes: RouteRecordRaw[] = [...baseRoutes]

if (APP_EDITION === 'enterprise') {
  // 使用动态导入，但不在顶层使用 await
  // 路由会在需要时懒加载
  try {
    // 这里使用同步导入检查，如果模块不存在会抛出错误
    // 但实际路由定义中使用懒加载
    const enterpriseRoute: RouteRecordRaw = {
      path: '/enterprise',
      name: 'enterprise',
      component: () => {
        // 使用动态导入，如果模块不存在会返回错误组件
        return import('../views/enterprise/enterpriseDashboard.vue').catch(() => {
          // 如果企业版页面不存在，返回一个占位组件
          return import('../views/ForbiddenView.vue')
        })
      },
      meta: { 
        requiresAuth: true, 
        roles: ['admin', 'user'],
        enterpriseOnly: true
      },
      children: [
        {
          path: 'analytics',
          name: 'enterpriseAnalytics',
          // @ts-ignore - 企业版文件可能不存在
          component: () => import('../views/enterprise/enterpriseAnalytics.vue').catch(() => {
            return import('../views/ForbiddenView.vue')
          }),
          meta: { 
            requiresAuth: true, 
            roles: ['admin'],
            enterpriseOnly: true
          }
        },
        {
          path: 'reports',
          name: 'enterpriseReports',
          // @ts-ignore - 企业版文件可能不存在
          component: () => import('../views/enterprise/enterpriseReports.vue').catch(() => {
            return import('../views/ForbiddenView.vue')
          }),
          meta: { 
            requiresAuth: true, 
            roles: ['admin', 'user'],
            enterpriseOnly: true
          }
        }
      ]
    }
    routes.push(enterpriseRoute)
    console.log('[路由] 企业版路由已添加')
  } catch (error) {
    // 企业版路由模块不存在时静默忽略，不报错
    console.warn('[路由] 企业版路由添加失败:', error)
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// 设置认证守卫
setupAuthGuards(router)

export default router
