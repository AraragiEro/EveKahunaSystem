import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { setupAuthGuards } from './guards'
import { getEnterpriseRoutes } from './enterprise'
import TodoListView from '../views/TodoListView.vue'
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
      path: '/landing',
      name: 'landing',
      component: () => import('../views/LandingPage.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/',
      redirect: '/landing'
    },
    {
      path: '/todolist',
      name: 'todolist',
      component: TodoListView,
      meta: { requiresAuth: true }
    },
    {
      path: '/home',
      name: 'home',
      component: HomeView,
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
const routes: RouteRecordRaw[] = [...baseRoutes, ...getEnterpriseRoutes(APP_EDITION)]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// 设置认证守卫
setupAuthGuards(router)

export default router
