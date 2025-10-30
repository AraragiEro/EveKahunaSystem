import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

export function setupAuthGuards(router: Router): void {
  router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore()
    
    // 检查是否需要认证
    if (to.meta.requiresAuth) {
      // 如果未认证，尝试检查认证状态
      if (!authStore.isAuthenticated) {
        const isAuthValid = await authStore.checkAuth()
        if (!isAuthValid) {
          next('/login')
          return
        }
      }
      
      // 检查角色权限
      if (to.meta.roles && !to.meta.roles.includes(authStore.userRole as string)) {
        next('/forbidden')
        return
      }
    }
    
    next()
  })
}