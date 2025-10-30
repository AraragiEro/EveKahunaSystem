import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

export interface User {
  id: string
  username: string
  email: string
  role: string
}

export interface LoginCredentials {
  username: string
  password: string
}

/**
 * defineStore 是 Pinia（Vue 官方推荐的状态管理库）中用于定义一个“store”的方法。
 * 
 * 它的作用类似于 Vuex 的 createStore，但语法更简洁、类型推断更好，且支持组合式 API。
 * 
 * 你可以把 defineStore 理解为“定义全局状态模块”的工厂函数。
 * 
 * 用法示例：
 * 
 * export const useAuthStore = defineStore('auth', () => {
 *   // 这里写 state、getter、action
 *   // ...
 *   return { ... }
 * })
 * 
 * 这样定义后，在组件或其他地方通过 useAuthStore() 就能访问和操作这个 store 里的状态和方法。
 * 
 * 详细文档见：https://pinia.vuejs.org/
 */
/**
 * 这是一个 Pinia Store，用于管理用户认证相关的全局状态。
 * Pinia 是 Vue 官方推荐的状态管理库，类似于 Vuex，但更轻量、类型推断更好。
 * 
 * 你可以把 Store 理解为一个全局的“数据仓库”，
 * 里面可以存放状态（state）、计算属性（getter）、方法（action）。
 * 
 * 这里我们用 defineStore 定义了一个名为 'auth' 的 Store，专门处理登录、登出、用户信息等认证逻辑。
 */
export const useAuthStore = defineStore('auth', () => {
  // -------------------- 状态（state） --------------------
  /**
   * user: 当前登录的用户信息，类型为 User 或 null。
   * ref 是 Vue 3 的响应式 API，user.value 变化时，使用它的组件会自动更新。
   */
  const user = ref<User | null>(null)

  /**
   * token: 登录后后端返回的认证 token。
   * localStorage 是浏览器提供的一种本地存储机制，可以将数据以键值对的形式永久保存在用户的浏览器中。
   * 即使刷新页面或关闭浏览器，数据也不会丢失，除非主动清除。
   * 这里我们尝试从 localStorage 读取 token，实现“自动登录”或“记住登录状态”的效果。
   */
  const token = ref<string | null>(localStorage.getItem('auth_token'))

  /**
   * isLoading: 标记当前是否正在进行登录等异步操作，用于页面上显示加载动画。
   */
  const isLoading = ref(false)

  /**
   * error: 记录最近一次操作的错误信息（如登录失败），用于页面上展示错误提示。
   */
  const error = ref<string | null>(null)

  // -------------------- 计算属性（getter） --------------------
  /**
   * isAuthenticated: 是否已认证（已登录）。
   * 只有 token 和 user 都存在时才算登录成功。
   * computed 是 Vue 的计算属性，依赖的值变化时会自动重新计算。
   */
  const isAuthenticated = computed(() => !!token.value && !!user.value)

  /**
   * userRole: 当前用户的角色（如 'admin'、'user'），未登录时为 'guest'。
   * 方便在页面或路由守卫中做权限判断。
   */
  const userRole = computed(() => user.value?.role || 'guest')

  // -------------------- 方法（action） --------------------
  /**
   * login: 登录方法，接收用户名和密码，向后端发送请求。
   * 登录成功后保存 token 和用户信息到状态和 localStorage。
   * 登录失败时设置 error 信息。
   */
  const login = async (credentials: LoginCredentials) => {
    isLoading.value = true      // 开始加载动画
    error.value = null          // 清空之前的错误

    try {
      // 向后端发送登录请求
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(credentials),
      })

      // 如果响应不是 2xx，抛出错误
      if (!response.ok) {
        throw new Error('登录失败')
      }

      // 解析后端返回的数据（应包含 token 和 user 信息）
      const data = await response.json()

      // 保存 token 和用户信息到状态和 localStorage
      token.value = data.token
      user.value = data.user
      localStorage.setItem('auth_token', data.token)

      return { success: true }
    } catch (err) {
      // 捕获错误，设置 error 信息，便于页面展示
      error.value = err instanceof Error ? err.message : '登录失败'
      return { success: false, error: error.value }
    } finally {
      isLoading.value = false   // 无论成功失败都结束加载动画
    }
  }

  /**
   * logout: 登出方法，清空用户信息和 token，并从 localStorage 移除 token。
   * 页面会自动变为未登录状态。
   */
  const logout = () => {
    user.value = null
    token.value = null
    localStorage.removeItem('auth_token')
  }

  /**
   * checkAuth: 检查当前 token 是否有效（比如页面刷新后）。
   * 会向后端请求当前用户信息，如果 token 无效则自动登出。
   * 通常在路由守卫或页面初始化时调用。
   */
  const checkAuth = async () => {
    // 没有 token 直接返回未认证
    if (!token.value) return false

    try {
      // 用 token 请求当前用户信息
      const response = await fetch('/api/auth/me', {
        headers: {
          'Authorization': `Bearer ${token.value}`
        }
      })

      if (response.ok) {
        // token 有效，保存用户信息
        const userData = await response.json()
        user.value = userData
        return true
      } else {
        // token 无效，自动登出
        logout()
        return false
      }
    } catch (err) {
      // 网络等异常也自动登出
      logout()
      return false
    }
  }

  /**
   * clearError: 清空错误信息，通常在用户关闭错误提示时调用。
   */
  const clearError = () => {
    error.value = null
  }

  // -------------------- 返回 Store 的所有属性和方法 --------------------
  // 这样在组件中 useAuthStore() 就能访问这些状态和方法
  return {
    // 状态
    user,
    token,
    isLoading,
    error,

    // 计算属性
    isAuthenticated,
    userRole,

    // 方法
    login,
    logout,
    checkAuth,
    clearError
  }
})