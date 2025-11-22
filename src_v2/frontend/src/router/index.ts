import { createRouter, createWebHistory } from 'vue-router'
import { setupAuthGuards } from './guards'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
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
      path: '/setting/characterSetting/auth/close',
      name: 'characterAuthClose',
      component: () => import('../views/setting/characterAuthClose.vue'),
      meta: { requiresAuth: false }
    }
  ],
})

// 设置认证守卫
setupAuthGuards(router)

export default router
