import type { RouteRecordRaw } from 'vue-router'

/**
 * 企业版专用路由
 * 这些路由只在企业版中加载
 */
export const enterpriseRoutes: RouteRecordRaw[] = [
  {
    path: '/market',
    name: 'market',
    component: () => {
      return import('../views/enterprise/marketView.vue').catch(() => {
        return import('../views/ForbiddenView.vue')
      })
    },
    meta: { 
      requiresAuth: true, 
      roles: ['vip_omega'],
      enterpriseOnly: true
    }
  }
]

/**
 * 根据版本获取企业版路由
 * @param edition 应用版本 ('enterprise' | 'community')
 * @returns 企业版路由数组，如果不是企业版则返回空数组
 */
export function getEnterpriseRoutes(edition: string): RouteRecordRaw[] {
  if (edition === 'enterprise') {
    try {
      console.log('[路由] 企业版路由已添加')
      return enterpriseRoutes
    } catch (error) {
      // 企业版路由模块不存在时静默忽略，不报错
      console.warn('[路由] 企业版路由添加失败:', error)
      return []
    }
  }
  return []
}

