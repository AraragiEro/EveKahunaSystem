import { ElMessage } from 'element-plus'

/**
 * 统一的 API 响应处理函数
 * @param response HTTP 响应对象
 * @param errorMessage 默认错误消息（当响应中没有 message 时使用）
 * @returns 解析后的响应数据，如果失败则返回 null
 */
export async function handleApiResponse<T = any>(
  response: { ok: boolean; json: () => Promise<any> },
  errorMessage: string = '操作失败'
): Promise<T | null> {
  try {
    const data = await response.json()
    
    // 检查响应体中的 status 字段
    if (data.status !== 200) {
      const message = data.message || errorMessage
      ElMessage.error(message)
      return null
    }
    
    return data as T
  } catch (error) {
    ElMessage.error(errorMessage)
    return null
  }
}

/**
 * 检查 API 响应是否成功（不显示错误消息）
 * @param data 响应数据
 * @returns 是否成功
 */
export function isApiSuccess(data: any): boolean {
  return data && data.status === 200
}

/**
 * 获取 API 响应中的错误消息
 * @param data 响应数据
 * @param defaultMessage 默认错误消息
 * @returns 错误消息
 */
export function getApiErrorMessage(data: any, defaultMessage: string = '操作失败'): string {
  return data?.message || defaultMessage
}

