import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useEdition } from '@/composables/useEdition'

export function setupAuthGuards(router: Router): void {
  router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore()
    const { isEnterprise } = useEdition()
    
    // 定义公开页面列表（不需要认证即可访问）
    const publicPages = ['/login', '/forbidden', '/setting/characterSetting/auth/close']
    // 支持动态路径匹配：/storage/:sid
    const isPublicPage = publicPages.includes(to.path) || to.path.startsWith('/storage/')
    
    // 如果已经登录，访问登录页时跳转到首页
    if (to.path === '/login' && authStore.isAuthenticated) {
      next('/home')
      return
    }
    
    // 如果不是公开页面，检查认证状态（默认所有页面都需要认证）
    if (!isPublicPage) {
      // 如果已经有 token 和 user，并且是刚刚登录（从登录页跳转过来）
      // 直接通过，因为登录接口已经验证了用户身份，不需要再次验证
      // 检查 user 和 token 而不仅仅是 isAuthenticated，确保即使响应式更新延迟也能正确识别
      if ((authStore.user && authStore.token) && from.path === '/login') {
        next()
        return
      }
      
      // 如果已经有 token 和 user，说明已经登录成功
      // 此时可以直接通过，因为登录接口已经验证了用户身份
      // checkAuth 会在 checkAuth 内部使用缓存机制避免重复请求
      if (!authStore.isAuthenticated) {
        // 没有 token 或 user，尝试从 localStorage 恢复
        const savedToken = localStorage.getItem('auth_token')
        if (!savedToken) {
          next('/login')
          return
        }
      }
      
      // 向服务端校验，防止本地状态被篡改
      // checkAuth 内部有缓存机制，不会频繁请求
      // 注意：如果是从登录页跳转过来的，上面已经直接通过了，不会执行到这里
      const isAuthValid = await authStore.checkAuth()
      if (!isAuthValid) {
        next('/login')
        return
      }

      // 增加角色权限检查（仅作为UI提示，后端仍需验证）
      if (to.meta.roles && (to.meta.roles as string[]).length > 0) {
        const userRoles = authStore.userRoles
        const hasRole = (to.meta.roles as string[]).some((role: string) => userRoles.includes(role))
        
        if (!hasRole) {
          next('/forbidden')  // 跳转到403页面
          return
        }
      }

      // 检查企业版路由访问权限
      if (to.meta.enterpriseOnly === true && !isEnterprise) {
        next('/forbidden')  // 非企业版访问企业版路由时跳转到403页面
        return
      }
    }
    
    next()
  })
}

export function haveRole(role: string): boolean {
  const authStore = useAuthStore()
  return authStore.user?.roles.includes(role) || false
}