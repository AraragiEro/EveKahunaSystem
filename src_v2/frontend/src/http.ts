// 这里的@是Vite等前端构建工具中配置的路径别名，通常代表src目录，方便引用文件。
// 例如 '@/stores/auth' 实际等价于 'src/stores/auth'
import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { useAuthStore } from '@/stores/auth'
import {
  buildCacheKey,
  clearInflightRequest,
  clearResponseCache,
  getCacheGeneration,
  getInflightRequest,
  readResponseCache,
  setInflightRequest,
  writeResponseCache,
} from '@/utils/responseCache'

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
      timeout: 120000,
      headers: {
        'Content-Type': 'application/json'
      },
      // 保持与 fetch 一致：即使是 4xx/5xx 也走 resolve，避免打破现有调用方对 response.ok 的判断
      validateStatus: () => true
    })

    // 从 cookie 中读取值
    function getCookie(name: string): string | null {
      const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`))
      return match ? decodeURIComponent(match[2]) : null
    }

    // 请求拦截器：注入 CSRF token（cookie 由后端 Set-Cookie 自动管理）
    this.client.interceptors.request.use((config) => {
      const method = (config.method || 'GET').toUpperCase()
      if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
        const csrfToken = getCookie('csrf_token')
        if (csrfToken) {
          config.headers = {
            ...(config.headers as any),
            'X-CSRF-Token': csrfToken,
          }
        }
      }
      return config
    })

    // 响应拦截器：401 自动刷新 token + 重试
    let isRefreshing = false
    let refreshPromise: Promise<boolean> | null = null

    this.client.interceptors.response.use(
      async (response) => {
        const status = response.status
        const authStore = useAuthStore()

        if (status === 401) {
          // 身份已失效：立刻清空只读接口缓存，避免登出后继续读到旧数据
          clearResponseCache()

          // 排除刷新端点本身（避免死循环）
          const reqUrl = response.config?.url || ''
          if (reqUrl === '/auth/refresh') {
            authStore.logout()
            return response
          }

          // 防止并发刷新
          if (!isRefreshing) {
            isRefreshing = true
            refreshPromise = (async () => {
              try {
                const refreshResp = await this.client.post('/auth/refresh')
                return refreshResp.status === 200
              } catch {
                return false
              } finally {
                isRefreshing = false
                refreshPromise = null
              }
            })()
          }

          const refreshed = await refreshPromise
          if (refreshed && response.config) {
            // 重试原请求
            return this.client.request(response.config)
          }

          authStore.logout()
        } else if (status === 403) {
          // 资产模块的 403 是业务权限不足（如公司任务归属），由页面提示，不做整页跳转
          const reqUrl = response.config?.url || ''
          if (!reqUrl.startsWith('/EVE/asset/')) {
            window.location.href = '/forbidden'
          }
        }

        return response
      },
      (error) => {
        // 网络错误不处理
        return Promise.reject(error)
      }
    )
  }

  /**
   * 从已序列化的请求体还原出参数对象，用于拼缓存键。
   * 解析失败时返回 undefined（该请求仍可走白名单，但键里不含参数——因此宁可返回原串）。
   */
  private parseCachePayload(body: unknown): unknown {
    if (body === undefined) return undefined
    if (typeof body !== 'string') return body
    try {
      return JSON.parse(body)
    } catch {
      return body
    }
  }

  /**
   * 统一出口：按白名单做「响应缓存 + 并发去重」，非白名单接口直接透传。
   * 安全约束见 utils/responseCache.ts 文件头注释。
   */
  private async dispatch(
    config: AxiosRequestConfig,
    cacheKey: string | null,
  ): Promise<AxiosResponse> {
    if (!cacheKey) {
      return this.client.request(config)
    }

    // 1) 缓存命中直接返回（深拷贝，避免调用方污染缓存）
    const cached = readResponseCache(cacheKey)
    if (cached) return cached

    // 2) 同键请求正在进行中：复用同一个 Promise，避免重复付费
    const inflight = getInflightRequest(cacheKey)
    if (inflight) return inflight

    const generation = getCacheGeneration()
    const promise = this.client
      .request(config)
      .then((res) => {
        // 只缓存 200；generation 用于丢弃清空缓存后返回的旧结果
        writeResponseCache(cacheKey, res, generation)
        return res
      })
      .finally(() => {
        clearInflightRequest(cacheKey)
      })

    setInflightRequest(cacheKey, promise)
    return promise
  }

  /** 供 auth store 在登出/用户切换时调用 */
  clearCache(): void {
    clearResponseCache()
  }

  private async request(endpoint: string, options: RequestInit = {}) {
    const config: AxiosRequestConfig = {
      url: endpoint,
      method: (options.method as AxiosRequestConfig['method']) || 'GET',
      headers: options.headers as AxiosRequestConfig['headers'],
      data: undefined,
      signal: (options as any).signal,
    }

    // fetch 的 body 可能已是字符串；axios 支持对象/字符串，字符串视为已序列化 JSON
    if (options.body !== undefined) {
      config.data = options.body
    }

    const cacheKey = buildCacheKey(
      String(config.method || 'GET'),
      endpoint,
      this.parseCachePayload(options.body),
    )
    const res = await this.dispatch(config, cacheKey)
    return new AxiosResponseAdapter(res)
  }

  async get(endpoint: string, data?: any, signal?: AbortSignal) {
    const config: AxiosRequestConfig = {
      url: endpoint,
      method: 'GET',
      signal,
    }

    // GET 请求将 data 转换为查询参数
    if (data !== undefined) {
      config.params = data
    }

    const cacheKey = buildCacheKey('GET', endpoint, data)
    const res = await this.dispatch(config, cacheKey)
    return new AxiosResponseAdapter(res)
  }

  async post(endpoint: string, data?: any, signal?: AbortSignal) {
    return this.request(endpoint, {
      method: 'POST',
      body: data !== undefined ? JSON.stringify(data) : undefined,
      signal,
    } as any)
  }

  async put(endpoint: string, data?: any, signal?: AbortSignal) {
    return this.request(endpoint, {
      method: 'PUT',
      body: data !== undefined ? JSON.stringify(data) : undefined,
      signal,
    } as any)
  }

  async patch(endpoint: string, data?: any, signal?: AbortSignal) {
    return this.request(endpoint, {
      method: 'PATCH',
      body: data !== undefined ? JSON.stringify(data) : undefined,
      signal,
    } as any)
  }

  async delete(endpoint: string, data?: any, signal?: AbortSignal) {
    return this.request(endpoint, {
      method: 'DELETE',
      body: data !== undefined ? JSON.stringify(data) : undefined,
      signal,
    } as any)
  }
}

export const http = new HttpService()