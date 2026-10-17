/**
 * 只读接口响应缓存（白名单制）
 *
 * ======================== 安全约束（修改前务必阅读） ========================
 *
 * 1. 默认拒绝：只有 CACHEABLE_ENDPOINTS 白名单内的接口才会被缓存。
 *    绝对不要改成「自动缓存所有 GET/POST」—— 那会引入跨用户数据泄露。
 *
 * 2. 白名单只允许放「无身份语义」的纯字典接口，即：
 *    响应结果**只由请求参数决定**，与当前登录用户、权限、计划 ID 无关。
 *
 *    已核实（后端 src_v2/backend/api/EVE/api_industry.py）：
 *      - getTypeSuggestionsList → SdeUtils.fuzz_type(type_name)，纯 SDE 静态数据
 *      - getGroupSuggestions     → SdeUtils.fuzz_xxx(assign_type, query)，纯 SDE 静态数据
 *        注意：该接口虽然取了 g.current_user["user_id"]，但并未传入实现函数，
 *        结果与用户无关，因此可以缓存。若未来实现改为按用户过滤，必须立即移出白名单。
 *
 *    明确**不得**加入白名单的接口（含身份语义，加了就是越权漏洞）：
 *      - /auth/*                      当前登录身份
 *      - /user/*                      用户与角色列表
 *      - /permission/*                权限点/角色
 *      - getLocationFlagList          使用 g.current_user["user_id"] 查容器许可
 *      - getUserAllContainerPermission 用户级容器许可
 *      - getConfigFlowPresets         当前用户的预设列表
 *      - getPlanTableData             当前用户（或管理员可见全部）的计划
 *      - getStructureList             Redis key 带 user_id
 *
 * 3. 只缓存 HTTP 200 的响应，401/403/500 一律不缓存。
 *
 * 4. 登出、收到 401、用户身份切换时，必须调用 clearResponseCache() 全量清空。
 *    本模块同时维护 generation 计数，清空后旧的在途请求不会再把结果写回缓存。
 *
 * 5. 缓存键 = 方法 + 完整 endpoint + 请求体（键排序后序列化），
 *    避免 {"query":"a"} 与 {"query":"b"} 相互污染。
 *
 * 6. 命中缓存时返回响应数据的深拷贝，防止调用方修改缓存内容影响后续使用者。
 * ==========================================================================
 */

import type { AxiosResponse } from 'axios'

/** 缓存有效期：60 秒。纯字典数据，短 TTL 足够且能限制脏数据存活时间 */
const CACHE_TTL_MS = 60 * 1000

/** 缓存条目上限，防止长会话内存膨胀 */
const CACHE_MAX_ENTRIES = 200

/**
 * 允许缓存的后端接口白名单。
 * 只放「响应结果仅由请求参数决定」的纯字典查询，详见文件头注释。
 */
const CACHEABLE_ENDPOINTS = new Set<string>([
  '/EVE/industry/getTypeSuggestionsList',
  '/EVE/industry/getGroupSuggestions',
])

interface CacheEntry {
  response: AxiosResponse
  expiresAt: number
}

const responseCache = new Map<string, CacheEntry>()
const inflightRequests = new Map<string, Promise<AxiosResponse>>()

/** 清空缓存时自增；在途请求写缓存前会比对，避免清空后又被旧请求写回 */
let cacheGeneration = 0

/**
 * 稳定序列化：对象键排序后再序列化，保证同样的参数生成同样的键。
 */
function stableStringify(value: unknown): string {
  if (value === null || value === undefined) return ''
  const type = typeof value
  if (type === 'string' || type === 'number' || type === 'boolean') return String(value)
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  if (type === 'object') {
    const obj = value as Record<string, unknown>
    const keys = Object.keys(obj).sort()
    return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`).join(',')}}`
  }
  return ''
}

/**
 * 构造缓存键。返回 null 表示该请求不在白名单内，不参与缓存与去重。
 */
export function buildCacheKey(
  method: string,
  endpoint: string,
  payload?: unknown,
): string | null {
  if (!endpoint) return null
  // 白名单匹配只看路径部分，查询串交给 payload/endpoint 一起参与键
  const pathPart = endpoint.split('?')[0]
  if (!CACHEABLE_ENDPOINTS.has(pathPart)) return null
  return `${method.toUpperCase()} ${endpoint} ${stableStringify(payload)}`
}

/** 深拷贝响应数据，避免调用方污染缓存 */
function cloneResponse(response: AxiosResponse): AxiosResponse {
  let data = response.data
  try {
    data = response.data === undefined ? undefined : JSON.parse(JSON.stringify(response.data))
  } catch {
    // 非 JSON 可序列化数据时退化为原引用（白名单内接口均为 JSON）
  }
  return { ...response, data }
}

/** 读取缓存，未命中或已过期返回 null */
export function readResponseCache(key: string): AxiosResponse | null {
  const entry = responseCache.get(key)
  if (!entry) return null
  if (entry.expiresAt <= Date.now()) {
    responseCache.delete(key)
    return null
  }
  return cloneResponse(entry.response)
}

/**
 * 写入缓存。generation 必须取自请求发起时的快照：
 * 若期间发生过 clearResponseCache()，本次结果会被丢弃。
 */
export function writeResponseCache(
  key: string,
  response: AxiosResponse,
  generation: number,
): void {
  if (generation !== cacheGeneration) return
  if (!response || response.status !== 200) return

  // 超出上限时淘汰最早插入的一条（Map 保持插入顺序）
  if (responseCache.size >= CACHE_MAX_ENTRIES) {
    const oldestKey = responseCache.keys().next().value
    if (oldestKey !== undefined) responseCache.delete(oldestKey)
  }
  responseCache.set(key, { response: cloneResponse(response), expiresAt: Date.now() + CACHE_TTL_MS })
}

/** 取进行中的同键请求，用于并发去重 */
export function getInflightRequest(key: string): Promise<AxiosResponse> | null {
  return inflightRequests.get(key) ?? null
}

export function setInflightRequest(key: string, promise: Promise<AxiosResponse>): void {
  inflightRequests.set(key, promise)
}

export function clearInflightRequest(key: string): void {
  inflightRequests.delete(key)
}

/** 当前缓存代次，请求发起时取快照 */
export function getCacheGeneration(): number {
  return cacheGeneration
}

/**
 * 全量清空缓存。
 * 调用时机：登出、收到 401、用户身份变化。
 */
export function clearResponseCache(): void {
  cacheGeneration += 1
  responseCache.clear()
  inflightRequests.clear()
}
