import { http } from '@/http'
import type {
  TqStatus,
  CharacterEsiStatus,
  TestTokenResult,
  BucketStats,
  QueueDepth,
  UsageLogEntry,
} from '@/types/esiAdmin'

/** 获取 TQ 服务器状态 */
export async function getTqStatus(): Promise<TqStatus> {
  const res = await http.get('/admin/esi/tq-status')
  const data = await res.json()
  if (data.status === 200) return data.data as TqStatus
  throw new Error(data.message || '获取 TQ 状态失败')
}

/** 获取角色 ESI 令牌状态列表 — API 返回 {status, data: [...], total} */
export async function getCharacters(
  params?: { status?: string; page?: number; page_size?: number }
): Promise<{ items: CharacterEsiStatus[]; total: number }> {
  const res = await http.get('/admin/esi/characters', params)
  const data = await res.json()
  if (data.status === 200) return { items: data.data, total: data.total }
  throw new Error(data.message || '获取角色状态失败')
}

/** 测试指定角色的 ESI 令牌 */
export async function testCharacterToken(characterId: number): Promise<TestTokenResult> {
  const res = await http.post(`/admin/esi/characters/${characterId}/test`)
  const data = await res.json()
  if (data.status === 200) return data.data as TestTokenResult
  throw new Error(data.message || '测试令牌失败')
}

/** 获取 ESI 请求桶统计 */
export async function getBuckets(): Promise<BucketStats[]> {
  const res = await http.get('/admin/esi/buckets')
  const data = await res.json()
  if (data.status === 200) return data.data.pools as BucketStats[]
  throw new Error(data.message || '获取桶统计失败')
}

/** 获取 ESI 请求队列深度 */
export async function getQueueDepth(): Promise<QueueDepth> {
  const res = await http.get('/admin/esi/queue-depth')
  const data = await res.json()
  if (data.status === 200) return data.data as QueueDepth
  throw new Error(data.message || '获取队列深度失败')
}

/** 获取 ESI 使用日志 */
export async function getUsageLog(
  params?: { limit?: number; offset?: number }
): Promise<{ items: UsageLogEntry[]; total: number; has_more: boolean }> {
  const res = await http.get('/admin/esi/usage-log', params)
  const data = await res.json()
  if (data.status === 200) return data.data as { items: UsageLogEntry[]; total: number; has_more: boolean }
  throw new Error(data.message || '获取使用日志失败')
}
