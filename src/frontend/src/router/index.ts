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
          path: 'userSetting',
          name: 'userSetting',
          component: () => import('../views/setting/userSetting.vue'),
          meta: { requiresAuth: true, roles: ['admin'] }
        },
        {
          path: 'industrySetting',
          name: 'industrySetting',
          component: () => import('../views/setting/industrySetting.vue'),
          meta: { requiresAuth: true, roles: ['admin', 'user'] }
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
      path: '/forbidden',
      name: 'forbidden',
      component: () => import('../views/ForbiddenView.vue'),
      meta: { requiresAuth: false }
    }
  ],
})

// 设置认证守卫
setupAuthGuards(router)

export default router
