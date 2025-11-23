// 这里的@是Vite等前端构建工具中配置的路径别名，通常代表src目录，方便引用文件。
// 例如 '@/stores/auth' 实际等价于 'src/stores/auth'
import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { useAuthStore } from '@/stores/auth'

// 适配器：将 AxiosResponse 适配为接近 fetch Response 的对象
class AxiosResponseAdapter {
  status: number
  ok: boolean
  private readonly data: any
  private readonly raw: AxiosResponse

  constructor(res: AxiosResponse) {
    this.status = res.status
    this.ok = res.status >= 200 && res.status < 300
    this.data = res.data
    this.raw = res
  }

  async json() {
    return this.data
  }

  async text() {
    if (typeof this.data === 'string') return this.data
    try {
      return JSON.stringify(this.data)
    } catch {
      return ''
    }
  }

  // 简单的 clone：返回新的适配器实例引用同一底层响应
  clone() {
    return new AxiosResponseAdapter(this.raw)
  }
}

// 使用 axios 的封装
class HttpService {
  private baseURL: string
  private client: AxiosInstance

  constructor(baseURL: string = '/api') {
    this.baseURL = baseURL
    this.client = axios.create({
      baseURL: this.baseURL,
      headers: {
        'Content-Type': 'application/json'
      },
      // 保持与 fetch 一致：即使是 4xx/5xx 也走 resolve，避免打破现有调用方对 response.ok 的判断
      validateStatus: () => true
    })

    // 请求拦截器：注入认证头
    this.client.interceptors.request.use((config) => {
      const authStore = useAuthStore()
      if (authStore.token) {
        config.headers = {
          ...(config.headers as any),
          Authorization: `Bearer ${authStore.token}`
        }
      }
      return config
    })

    // 响应拦截器：统一处理 401 / 403
    this.client.interceptors.response.use((response) => {
      const status = response.status
      const authStore = useAuthStore()

      if (status === 401) {
        authStore.logout()
        window.location.href = '/login'
      } else if (status === 403) {
        window.location.href = '/forbidden'
      }

      return response
    })
  }

  private async request(endpoint: string, options: RequestInit = {}) {
    const config: AxiosRequestConfig = {
      url: endpoint,
      method: (options.method as AxiosRequestConfig['method']) || 'GET',
      headers: options.headers as AxiosRequestConfig['headers'],
      data: undefined
    }

    // fetch 的 body 可能已是字符串；axios 支持对象/字符串，字符串视为已序列化 JSON
    if (options.body !== undefined) {
      config.data = options.body
    }

    const res = await this.client.request(config)
    return new AxiosResponseAdapter(res)
  }

  async get(endpoint: string, data?: any) {
    return this.request(endpoint, { method: 'GET', body: data !== undefined ? JSON.stringify(data) : undefined })
  }

  async post(endpoint: string, data?: any) {
    return this.request(endpoint, {
      method: 'POST',
      // 与现有调用方兼容：传入对象时保持 JSON 字符串
      body: data !== undefined ? JSON.stringify(data) : undefined
    })
  }

  async put(endpoint: string, data?: any) {
    return this.request(endpoint, {
      method: 'PUT',
      body: data !== undefined ? JSON.stringify(data) : undefined
    })
  }

  async delete(endpoint: string, data?: any) {
    return this.request(endpoint, {
      method: 'DELETE',
      body: data !== undefined ? JSON.stringify(data) : undefined
    })
  }
}

export const http = new HttpService()