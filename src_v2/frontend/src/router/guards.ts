import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useEdition } from '@/composables/useEdition'

export function setupAuthGuards(router: Router): void {
  router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore()
    const { isEnterprise } = useEdition()
    
    // 定义公开页面列表（不需要认证即可访问）
    const publicPages = ['/', '/login', '/landing', '/announcements', '/forbidden', '/setting/characterSetting/auth/close']
    // 支持动态路径匹配：/storage/:sid 和 /workflow/:token
    const isPublicPage = publicPages.includes(to.path) || to.path.startsWith('/storage/') || to.path.startsWith('/workflow/')
    
    // 如果访问登录页，检查是否已经登录（验证 token 有效性）
    if (to.path === '/login') {
      // 如果有 token，验证其有效性
      if (authStore.token) {
        const isAuthValid = await authStore.checkAuth()
        if (isAuthValid) {
          // token 有效，已登录，重定向到首页
          //如果是alpha或以上，跳转home，否则todolist
          if (authStore.user?.roles.includes('vip_alpha') || authStore.user?.roles.includes('vip_omega')) {
            next('/home')
            return
          } else {
            next('/todolist')
            return
          }
        }
        // token 无效，checkAuth 已自动清除状态，允许访问登录页
      }
      // 没有 token，允许访问登录页
      next()
      return
    }
    
    // 如果不是公开页面，检查认证状态（默认所有页面都需要认证）
    if (!isPublicPage) {
      // 如果已经有 token 和 user，并且是刚刚登录（从登录页跳转过来）
      // 仍然需要调用 checkAuth 获取完整的用户信息（包括完整的 roles）
      // 因为登录接口可能返回不完整的用户数据（如 omega 用户缺少 alpha 角色）
      if ((authStore.user && authStore.token) && from.path === '/login') {
        // 清除登录时设置的缓存，强制调用 checkAuth 获取完整的用户信息
        // 因为登录接口返回的数据可能不完整（如 omega 用户缺少 alpha 角色）
        authStore.clearAuthCache()
        // 调用 checkAuth 获取完整的用户信息
        const isAuthValid = await authStore.checkAuth()
        if (!isAuthValid) {
          next('/login')
          return
        }
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
