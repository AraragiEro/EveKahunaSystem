// ESI 管理员状态页面类型定义

/** 角色 ESI 令牌状态 — 字段名严格匹配 API 响应 */
export interface CharacterEsiStatus {
  character_id: number
  character_name: string
  owner_user_name: string
  birthday: string | null
  expires_time: string | null
  corporation_id: number | null
  director: boolean
  token_status: 'valid' | 'about_to_expire' | 'expired' | 'unknown'
}

/** ESI 请求桶统计（单个池） */
export interface BucketStats {
  pool_name: string
  rate: number
  max: number
  remaining: number
  error_count: number
  endpoints: string[]
}

/** ESI 请求队列深度 */
export interface QueueDepth {
  backlog: number
  in_flight: number
}

/** ESI 使用日志条目 */
export interface UsageLogEntry {
  id: number
  timestamp: string
  endpoint: string
  pool_name: string
  character_id: number | null
  status_code: number | null
  latency_ms: number | null
  error_message: string | null
}

/** TQ (Tranquility) 服务器状态 */
export interface TqStatus {
  status: 'online' | 'offline' | 'unknown'
}

/** 测试令牌结果 — 字段名严格匹配 API 响应 */
export interface TestTokenResult {
  success: boolean
  latency_ms: number
  status_code: number | null
  error: string | null
  character_name?: string | null
}
