// 设施系数监控模块类型定义

/** 已监控星系信息 */
export interface WatchedSystem {
  system_id: number
  system_name: string
  system_name_zh?: string
  region_name?: string
  manufacturing: number | null
  reaction: number | null
}

/** 星系搜索结果 */
export interface SystemSearchResult {
  system_id: number
  system_name: string
  system_name_zh: string
}

/** 监控列表响应 */
export interface WatchlistResponse {
  status: number
  data: WatchedSystem[]
}

/** 星系搜索响应 */
export interface SearchSystemsResponse {
  status: number
  data: SystemSearchResult[]
  count: number
}

/** 添加监控星系请求 */
export interface AddSystemRequest {
  system_id: number
}

/** 批量添加全部结果响应 */
export interface AddAllResponse {
  status: number
  data: {
    added_count: number
    systems: SystemSearchResult[]
  }
  message: string
}
