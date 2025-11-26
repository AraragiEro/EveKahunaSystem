import type { RouteRecordRaw } from 'vue-router'

/**
 * 企业版专用路由
 * 这些路由只在企业版中加载
 */
export const enterpriseRoutes: RouteRecordRaw[] = [
  {
    path: '/enterprise',
    name: 'enterprise',
    component: () => import('../views/enterprise/enterpriseDashboard.vue'),
    meta: { 
      requiresAuth: true, 
      roles: ['admin', 'user'],
      enterpriseOnly: true  // 标记为企业版专用
    },
    children: [
      {
        path: 'analytics',
        name: 'enterpriseAnalytics',
        component: () => import('../views/enterprise/enterpriseAnalytics.vue'),
        meta: { 
          requiresAuth: true, 
          roles: ['admin'],
          enterpriseOnly: true
        }
      },
      {
        path: 'reports',
        name: 'enterpriseReports',
        component: () => import('../views/enterprise/enterpriseReports.vue'),
        meta: { 
          requiresAuth: true, 
          roles: ['admin', 'user'],
          enterpriseOnly: true
        }
      }
    ]
  }
]

