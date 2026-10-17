import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useEdition } from '@/composables/useEdition'

export function setupAuthGuards(router: Router): void {
  router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore()
    const { isEnterprise } = useEdition()
    
    // 定义公开页面列表（不需要认证即可访问）
    const publicPages = ['/', '/login', '/landing', '/announcements', '/forbidden', '/setting/characterSetting/auth/close', '/utils/estimator', '/utils/piProfit']
    // 支持动态路径匹配：/storage/:sid 和 /workflow/:token
    const isPublicPage = publicPages.includes(to.path) || to.path.startsWith('/storage/') || to.path.startsWith('/workflow/')
    
    // 如果访问登录页，检查是否已经登录（验证 token 有效性）
    if (to.path === '/login') {
      // 如果有 token，验证其有效性
      if (authStore.isAuthenticated) {
        const isAuthValid = await authStore.checkAuth()
        if (isAuthValid) {
          // token 有效，已登录，重定向到首页
          // 登录成功，跳转仪表盘
          next('/dashboard')
          return
        }
        // token 无效，checkAuth 已自动清除状态，允许访问登录页
      }
      // 没有 token，允许访问登录页
      next()
      return
    }
    
    // 如果不是公开页面，检查认证状态（默认所有页面都需要认证）
    if (!isPublicPage) {
      // 需要「前台阻塞校验」的路由：管理员路由（meta.roles 非空）和企业版路由。
      // 这类页面若先渲染再被踢走，会暴露菜单结构与功能入口，因此保持原有阻塞语义。
      const rolesMeta = to.meta.roles as string[] | undefined
      const needsStrictCheck =
        (Array.isArray(rolesMeta) && rolesMeta.length > 0) || to.meta.enterpriseOnly === true

      // 如果已经有 token 和 user，并且是刚刚登录（从登录页跳转过来）
      // 仍然需要调用 checkAuth 获取完整的用户信息（包括完整的 roles）
      // 因为登录接口可能返回不完整的用户数据（如 omega 用户缺少 alpha 角色）
      if ((authStore.user && authStore.isAuthenticated) && from.path === '/login') {
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

      // 如果未认证，尝试通过 /auth/me 验证（cookie 自动发送）
      // user 只存在于内存（未持久化到 localStorage），因此首屏/新标签页必须阻塞确认身份，
      // 否则会先渲染受保护页面再被踢走。
      if (!authStore.isAuthenticated) {
        const isAuthValid = await authStore.checkAuth()
        if (!isAuthValid) {
          next('/login')
          return
        }
      } else if (needsStrictCheck) {
        // 管理员 / 企业版路由：保持前台阻塞校验，不接受界面闪现
        const isAuthValid = await authStore.checkAuth()
        if (!isAuthValid) {
          next('/login')
          return
        }
      } else {
        // 普通页面：立即放行，改为后台静默复核。
        // 复核仍受 checkAuth 内 30 秒 TTL 约束，撤权可见延迟与改造前一致，
        // 但不再让每一次页面切换都阻塞在这条跨境请求（实测约 677ms）上。
        // 复核失败时再跳转登录页；网络异常不打断当前页面，交由后续 API 的 401 处理。
        void authStore
          .checkAuth()
          .then((isAuthValid) => {
            if (!isAuthValid) router.replace('/login')
          })
          .catch(() => {
            /* 静默：不因复核网络抖动打断用户操作 */
          })
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
