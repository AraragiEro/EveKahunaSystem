import { ref, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { http } from '@/http'
import type { 
  ImplementationItem, 
  LocalImplementationState 
} from './useWorkflowImplementation'

/**
 * 冲突信息
 */
export interface Conflict {
  workflow_item_key: string
  server_value: {
    implemented: boolean
    runs_implemented?: number
    modified_at: string
  }
  resolution: 'use_server' | 'use_local'
}

/**
 * 同步状态
 */
export interface SyncState {
  isSyncing: boolean
  lastSyncTime: string | null
  conflicts: Conflict[]
  isOnline: boolean
}

/**
 * 服务器响应
 */
interface SyncResponse {
  status: number
  server_time: string
  conflicts?: Conflict[]
  server_only_items?: Array<{
    workflow_item_key: string
    implemented: boolean
    runs_implemented?: number
    modified_at: string
  }>
}

/**
 * 同步 composable
 * 
 * @param userName 用户名
 * @param planName 计划名称
 * @param calculationId 计算周期ID
 * @param implementations 本地实施状态
 * @param lastSynced 上次同步时间
 */
export function useWorkflowImplementationSync(
  userName: Ref<string>,
  planName: Ref<string | null>,
  calculationId: Ref<number | null>,
  implementations: Ref<Record<string, ImplementationItem>>,
  lastSynced: Ref<string | null>,
  options: {
    onConflict?: (conflicts: Conflict[]) => void
    onSyncSuccess?: () => void
  } = {}
) {
  // 同步状态
  const isSyncing = ref(false)
  const lastSyncTime = ref<string | null>(null)
  const conflicts = ref<Conflict[]>([])
  const isOnline = ref(navigator.onLine)

  // 定时器引用
  let syncTimer: number | null = null
  let debounceTimer: number | null = null

  /**
   * 获取待同步的变更
   */
  const getPendingChanges = () => {
    return Object.entries(implementations.value)
      .filter(([, item]) => item.syncStatus === 'pending')
      .map(([key, item]) => ({
        workflow_item_key: key,
        implemented: item.implemented,
        runs_implemented: item.runsImplemented,
        modified_at: item.modifiedAt
      }))
  }

  /**
   * 检查是否有待同步的变更
   */
  const hasPendingChanges = () => {
    return Object.values(implementations.value).some(item => item.syncStatus === 'pending')
  }

  /**
   * 执行同步
   */
  const syncNow = async (force: boolean = false): Promise<boolean> => {
    if (!planName.value || !userName.value || !calculationId.value) {
      return false
    }

    // 如果正在同步中，跳过
    if (isSyncing.value) {
      console.log('[WorkflowSync] 同步正在进行中，跳过')
      return false
    }

    // 如果没有待同步的变更且不是强制同步，跳过
    if (!hasPendingChanges() && !force) {
      return false
    }

    isSyncing.value = true
    console.log('[WorkflowSync] 开始同步...')

    try {
      const pendingChanges = getPendingChanges()
      
      const response = await http.post(
        `/EVE/industry/plan/${encodeURIComponent(planName.value)}/workflow/implementations/sync`,
        {
          calculation_id: calculationId.value,
          items: pendingChanges,
          deleted_keys: [] // TODO: 处理删除
        }
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const result: SyncResponse = await response.json()

      if (result.status !== 200) {
        throw new Error(`Server error: ${result.status}`)
      }

      // 处理冲突
      if (result.conflicts && result.conflicts.length > 0) {
        conflicts.value = result.conflicts
        console.log('[WorkflowSync] 检测到冲突:', result.conflicts)
        
        // 自动使用服务器版本解决冲突
        result.conflicts.forEach(conflict => {
          const item = implementations.value[conflict.workflow_item_key]
          if (item) {
            item.implemented = conflict.server_value.implemented
            item.runsImplemented = conflict.server_value.runs_implemented
            item.modifiedAt = conflict.server_value.modified_at
            item.syncStatus = 'synced'
          }
        })
        
        if (options.onConflict) {
          options.onConflict(result.conflicts)
        }
      }

      // 处理服务器独有的项（合并到本地）
      if (result.server_only_items && result.server_only_items.length > 0) {
        console.log('[WorkflowSync] 合并服务器项:', result.server_only_items.length)
        result.server_only_items.forEach(serverItem => {
          implementations.value[serverItem.workflow_item_key] = {
            implemented: serverItem.implemented,
            runsImplemented: serverItem.runs_implemented,
            modifiedAt: serverItem.modified_at,
            syncStatus: 'synced'
          }
        })
      }

      // 标记所有 pending 项为 synced
      Object.keys(implementations.value).forEach(key => {
        if (implementations.value[key].syncStatus === 'pending') {
          implementations.value[key].syncStatus = 'synced'
        }
      })

      lastSyncTime.value = result.server_time
      lastSynced.value = result.server_time
      
      console.log('[WorkflowSync] 同步成功')
      
      if (options.onSyncSuccess) {
        options.onSyncSuccess()
      }
      
      return true

    } catch (error) {
      console.error('[WorkflowSync] 同步失败:', error)
      // 同步失败，保持 pending 状态，等待下次重试
      return false
    } finally {
      isSyncing.value = false
    }
  }

  /**
   * 防抖同步（用于用户操作后）
   */
  const debouncedSync = (delay: number = 3000) => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
    }
    debounceTimer = window.setTimeout(() => {
      syncNow()
    }, delay)
  }

  /**
   * 从服务器获取实施状态（用于初始化加载）
   */
  const fetchFromServer = async (): Promise<boolean> => {
    if (!planName.value || !userName.value || !calculationId.value) {
      return false
    }

    console.log('[WorkflowSync] 从服务器加载状态...')

    try {
      const response = await http.get(
        `/EVE/industry/plan/${encodeURIComponent(planName.value)}/workflow/implementations?calculation_id=${calculationId.value}`
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const result = await response.json()

      if (result.status !== 200) {
        throw new Error(`Server error: ${result.status}`)
      }

      // GET 接口返回格式: { status: 200, data: { items: [], last_modified: ... } }
      interface GetResponse {
        status: number
        data: {
          calculation_id: number
          items: Array<{
            workflow_item_key: string
            implemented: boolean
            runs_implemented?: number
            modified_at: string
          }>
          last_modified: string | null
        }
      }
      
      const getResult = result as unknown as GetResponse
      // 过滤掉 implemented: false 的记录（服务器应该已经删除，但为了保险）
      const serverItems = (getResult.data?.items || []).filter(item => item.implemented)
      
      if (serverItems.length === 0) {
        console.log('[WorkflowSync] 服务器无数据')
        return true
      }

      console.log(`[WorkflowSync] 从服务器加载 ${serverItems.length} 条记录`)

      // 合并服务器数据到本地
      serverItems.forEach((serverItem) => {
        const localItem = implementations.value[serverItem.workflow_item_key]
        
        if (!localItem) {
          // 本地没有，使用服务器数据
          implementations.value[serverItem.workflow_item_key] = {
            implemented: serverItem.implemented,
            runsImplemented: serverItem.runs_implemented,
            modifiedAt: serverItem.modified_at,
            syncStatus: 'synced'
          }
        } else if (localItem.syncStatus === 'synced') {
          // 本地有且已同步，使用服务器数据（以服务器为准）
          const serverTime = new Date(serverItem.modified_at).getTime()
          const localTime = new Date(localItem.modifiedAt).getTime()
          
          if (serverTime > localTime) {
            localItem.implemented = serverItem.implemented
            localItem.runsImplemented = serverItem.runs_implemented
            localItem.modifiedAt = serverItem.modified_at
          }
        }
        // 如果本地是 pending 状态，保留本地数据（等待同步时解决冲突）
      })

      lastSyncTime.value = result.data?.last_modified || new Date().toISOString()
      
      console.log('[WorkflowSync] 加载完成')
      return true

    } catch (error) {
      console.error('[WorkflowSync] 从服务器加载失败:', error)
      return false
    }
  }

  /**
   * 启动定时同步
   */
  const startAutoSync = async (interval: number = 30000) => {
    // 清除现有定时器
    stopAutoSync()
    
    // 先从服务器获取初始状态
    await fetchFromServer()
    
    // 然后执行一次同步（上传本地 pending 的变更）
    await syncNow()
    
    // 启动定时器
    syncTimer = window.setInterval(() => {
      if (isOnline.value && hasPendingChanges()) {
        syncNow()
      }
    }, interval)
    
    console.log(`[WorkflowSync] 自动同步已启动，间隔: ${interval}ms`)
  }

  /**
   * 停止定时同步
   */
  const stopAutoSync = () => {
    if (syncTimer) {
      clearInterval(syncTimer)
      syncTimer = null
      console.log('[WorkflowSync] 自动同步已停止')
    }
  }

  /**
   * 页面关闭前强制同步
   */
  const syncBeforeUnload = () => {
    if (hasPendingChanges() && planName.value && calculationId.value) {
      const pendingChanges = getPendingChanges()
      const data = JSON.stringify({
        calculation_id: calculationId.value,
        items: pendingChanges,
        deleted_keys: []
      })
      
      navigator.sendBeacon(
        `/api/EVE/industry/plan/${encodeURIComponent(planName.value)}/workflow/implementations/sync`,
        new Blob([data], { type: 'application/json' })
      )
    }
  }

  /**
   * 解决冲突（手动选择）
   */
  const resolveConflict = (itemKey: string, useServer: boolean) => {
    const conflict = conflicts.value.find(c => c.workflow_item_key === itemKey)
    if (!conflict) return

    if (useServer) {
      // 使用服务器版本
      implementations.value[itemKey] = {
        implemented: conflict.server_value.implemented,
        runsImplemented: conflict.server_value.runs_implemented,
        modifiedAt: new Date().toISOString(),
        syncStatus: 'pending' // 标记为 pending 以便同步回服务器
      }
    } else {
      // 使用本地版本，标记为 pending 强制覆盖
      if (implementations.value[itemKey]) {
        implementations.value[itemKey].modifiedAt = new Date().toISOString()
        implementations.value[itemKey].syncStatus = 'pending'
      }
    }

    // 从冲突列表中移除
    conflicts.value = conflicts.value.filter(c => c.workflow_item_key !== itemKey)
    
    // 触发同步
    syncNow()
  }

  /**
   * 获取同步状态文本
   */
  const getSyncStatusText = () => {
    if (isSyncing.value) {
      return '同步中...'
    }
    if (conflicts.value.length > 0) {
      return `${conflicts.value.length} 个冲突`
    }
    if (hasPendingChanges()) {
      return '待同步'
    }
    if (lastSyncTime.value) {
      const date = new Date(lastSyncTime.value)
      return `已同步 ${date.toLocaleTimeString()}`
    }
    return '未同步'
  }

  // 监听网络状态
  const handleOnline = () => {
    isOnline.value = true
    console.log('[WorkflowSync] 网络已恢复')
    if (hasPendingChanges()) {
      syncNow()
    }
  }

  const handleOffline = () => {
    isOnline.value = false
    console.log('[WorkflowSync] 网络已断开')
  }

  // 监听页面可见性变化
  const handleVisibilityChange = () => {
    if (document.visibilityState === 'visible' && isOnline.value) {
      // 页面从后台切回前台，执行同步
      syncNow()
    }
  }

  // 注册事件监听
  const setupEventListeners = () => {
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    window.addEventListener('beforeunload', syncBeforeUnload)
    document.addEventListener('visibilitychange', handleVisibilityChange)
  }

  // 移除事件监听
  const removeEventListeners = () => {
    window.removeEventListener('online', handleOnline)
    window.removeEventListener('offline', handleOffline)
    window.removeEventListener('beforeunload', syncBeforeUnload)
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  }

  // 监听 implementations 变化，触发防抖同步
  watch(
    () => Object.keys(implementations.value).length,
    () => {
      if (hasPendingChanges()) {
        debouncedSync(3000)
      }
    }
  )

  // 组件挂载时设置事件监听
  setupEventListeners()

  return {
    // 状态
    isSyncing,
    lastSyncTime,
    conflicts,
    isOnline,
    
    // 方法
    syncNow,
    debouncedSync,
    startAutoSync,
    stopAutoSync,
    syncBeforeUnload,
    fetchFromServer,
    resolveConflict,
    getSyncStatusText,
    hasPendingChanges,
    setupEventListeners,
    removeEventListeners
  }
}
