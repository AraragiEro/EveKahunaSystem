// 这里的@是Vite等前端构建工具中配置的路径别名，通常代表src目录，方便引用文件。
// 例如 '@/stores/auth' 实际等价于 'src/stores/auth'
import { useAuthStore } from '@/stores/auth'

// 创建axios实例或使用fetch的封装
class HttpService {
  private baseURL: string

  constructor(baseURL: string = '/api') {
    this.baseURL = baseURL
  }

  private async request(endpoint: string, options: RequestInit = {}) {
    const authStore = useAuthStore()
    
    // 添加认证头
    if (authStore.token) {
      options.headers = {
        ...options.headers,
        'Authorization': `Bearer ${authStore.token}`
      }
    }

    const response = await fetch(`${this.baseURL}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      }
    })

    // 处理401未授权
    if (response.status === 401) {
      authStore.logout()
      window.location.href = '/login'
      throw new Error('未授权访问')
    }

    return response
  }

  async get(endpoint: string) {
    return this.request(endpoint, { method: 'GET' })
  }

  async post(endpoint: string, data?: any) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }

  async put(endpoint: string, data?: any) {
    return this.request(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  }

  async delete(endpoint: string) {
    return this.request(endpoint, { method: 'DELETE' })
  }
}

export const http = new HttpService()