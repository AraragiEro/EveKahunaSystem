import { ref, watch, type Ref } from 'vue'

/**
 * 实施状态同步状态
 */
export type SyncStatus = 'pending' | 'synced' | 'conflict'

/**
 * 单个工作流项的实施状态
 */
export interface ImplementationItem {
  implemented: boolean
  runsImplemented?: number
  modifiedAt: string
  syncStatus: SyncStatus
}

/**
 * 本地存储的完整状态结构
 */
export interface LocalImplementationState {
  version: number
  userName: string
  planName: string
  calculationId: number | null
  lastModified: string
  lastSynced: string | null
  items: Record<string, ImplementationItem>
  pendingDeletions: string[]
}

/**
 * 存储键前缀
 */
const STORAGE_KEY_PREFIX = 'kahuna_workflow_impl_v2_'

/**
 * 构建本地存储的 key
 */
const buildStorageKey = (userName: string, planName: string, calculationId: number | null): string => {
  return `${STORAGE_KEY_PREFIX}${userName}_${planName}_${calculationId ?? 'null'}`
}

/**
 * 生成工作流项的唯一 key
 * 格式: "{type_id}_{runs}_{fake}_{available}"
 */
export const getWorkflowItemKey = (item: {
  type_id: number
  runs: number
  fake?: boolean
  avaliable?: boolean
}): string => {
  const fake = item.fake ?? false
  const available = item.avaliable ?? false
  return `${item.type_id}_${item.runs}_${fake}_${available}`
}

/**
 * 工作流实施标记状态管理 composable
 * 
 * @param userName 用户名
 * @param planName 计划名称
 * @param calculationId 计算周期ID
 */
export function useWorkflowImplementation(
  userName: Ref<string>,
  planName: Ref<string | null>,
  calculationId: Ref<number | null>
) {
  // 实施状态映射表
  const implementations = ref<Record<string, ImplementationItem>>({})
  
  // 上次同步时间
  const lastSynced = ref<string | null>(null)
  
  // 上次修改时间
  const lastModified = ref<string>(new Date().toISOString())

  /**
   * 加载本地存储的状态
   */
  const loadLocalState = (): void => {
    if (!planName.value || !userName.value) {
      implementations.value = {}
      return
    }
    
    const key = buildStorageKey(userName.value, planName.value, calculationId.value)
    try {
      const saved = localStorage.getItem(key)
      if (saved) {
        const data = JSON.parse(saved) as LocalImplementationState
        // 验证数据版本
        if (data.version === 2) {
          implementations.value = data.items || {}
          lastSynced.value = data.lastSynced
          lastModified.value = data.lastModified
          console.log(`[WorkflowImpl] 已加载本地状态: ${key}, 条目数: ${Object.keys(implementations.value).length}`)
        } else {
          // 版本不匹配，清空
          console.warn(`[WorkflowImpl] 本地存储版本不匹配，重置状态`)
          implementations.value = {}
          lastSynced.value = null
        }
      } else {
        implementations.value = {}
        lastSynced.value = null
        console.log(`[WorkflowImpl] 无本地状态: ${key}`)
      }
    } catch (e) {
      console.error('[WorkflowImpl] 加载本地状态失败:', e)
      implementations.value = {}
      lastSynced.value = null
    }
  }

  /**
   * 保存到本地存储
   */
  const saveLocalState = (): void => {
    if (!planName.value || !userName.value) return
    
    const key = buildStorageKey(userName.value, planName.value, calculationId.value)
    const now = new Date().toISOString()
    lastModified.value = now
    
    const data: LocalImplementationState = {
      version: 2,
      userName: userName.value,
      planName: planName.value,
      calculationId: calculationId.value,
      lastModified: now,
      lastSynced: lastSynced.value,
      items: implementations.value,
      pendingDeletions: []
    }
    
    try {
      localStorage.setItem(key, JSON.stringify(data))
    } catch (e) {
      console.error('[WorkflowImpl] 保存本地状态失败:', e)
      // 如果是存储空间不足，尝试清理旧数据
      if ((e as Error).name === 'QuotaExceededError') {
        cleanupOldData()
        // 重试一次
        try {
          localStorage.setItem(key, JSON.stringify(data))
        } catch (retryError) {
          console.error('[WorkflowImpl] 重试保存失败:', retryError)
        }
      }
    }
  }

  /**
   * 标记工作流项为已实施
   */
  const markImplemented = (itemKey: string, runs?: number): void => {
    implementations.value[itemKey] = {
      implemented: true,
      runsImplemented: runs,
      modifiedAt: new Date().toISOString(),
      syncStatus: 'pending'
    }
    saveLocalState()
    console.log(`[WorkflowImpl] 标记已实施: ${itemKey}`)
  }

  /**
   * 取消标记工作流项
   */
  const unmarkImplemented = (itemKey: string): void => {
    // 标记为未实施，而不是删除，以便同步到服务器
    implementations.value[itemKey] = {
      implemented: false,
      runsImplemented: undefined,
      modifiedAt: new Date().toISOString(),
      syncStatus: 'pending'
    }
    saveLocalState()
    console.log(`[WorkflowImpl] 取消标记: ${itemKey}`)
  }

  /**
   * 设置部分实施运行次数
   */
  const setRunsImplemented = (itemKey: string, runs: number, totalRuns: number): void => {
    const clamped = Math.max(0, Math.min(runs, totalRuns))
    const isFull = clamped >= totalRuns
    implementations.value[itemKey] = {
      implemented: isFull,
      runsImplemented: clamped,
      modifiedAt: new Date().toISOString(),
      syncStatus: 'pending'
    }
    saveLocalState()
  }

  /**
   * 增加实施运行次数（累加模式）
   */
  const addMoreImplementation = (itemKey: string, additionalRuns: number, totalRuns: number): void => {
    const current = implementations.value[itemKey]?.runsImplemented ?? 0
    const newTotal = current + additionalRuns
    setRunsImplemented(itemKey, newTotal, totalRuns)
  }

  /**
   * 获取部分实施进度信息
   */
  const getPartialProgress = (itemKey: string, totalRuns: number): {
    implemented: number
    total: number
    remaining: number
    isPartial: boolean
    isFullyImplemented: boolean
  } => {
    const implemented = Math.max(0, Math.min(implementations.value[itemKey]?.runsImplemented ?? 0, totalRuns))
    const total = totalRuns
    return {
      implemented,
      total,
      remaining: total - implemented,
      isPartial: implemented > 0 && implemented < total,
      isFullyImplemented: implemented >= total
    }
  }

  /**
   * 安全获取已实施运行次数（防 localStorage 脏数据溢出）
   */
  const getRunsImplementedDisplay = (itemKey: string, totalRuns: number): number => {
    return Math.max(0, Math.min(implementations.value[itemKey]?.runsImplemented ?? 0, totalRuns))
  }

  /**
   * 切换工作流项的实施状态
   */
  const toggleImplemented = (itemKey: string, runs?: number): boolean => {
    if (isImplemented(itemKey)) {
      unmarkImplemented(itemKey)
      return false
    } else {
      markImplemented(itemKey, runs)
      return true
    }
  }

  /**
   * 检查工作流项是否已实施
   */
  const isImplemented = (itemKey: string): boolean => {
    return implementations.value[itemKey]?.implemented || false
  }

  /**
   * 获取已实施的运行次数
   */
  const getRunsImplemented = (itemKey: string): number | undefined => {
    return implementations.value[itemKey]?.runsImplemented
  }

  /**
   * 检查是否有待同步的数据
   */
  const hasPendingChanges = (): boolean => {
    return Object.values(implementations.value).some(item => item.syncStatus === 'pending')
  }

  /**
   * 更新同步状态
   */
  const updateSyncStatus = (itemKey: string, status: SyncStatus): void => {
    if (implementations.value[itemKey]) {
      implementations.value[itemKey].syncStatus = status
      saveLocalState()
    }
  }

  /**
   * 设置所有 pending 项为 synced
   */
  const markAllAsSynced = (): void => {
    Object.keys(implementations.value).forEach(key => {
      if (implementations.value[key].syncStatus === 'pending') {
        implementations.value[key].syncStatus = 'synced'
      }
    })
    lastSynced.value = new Date().toISOString()
    saveLocalState()
  }

  /**
   * 从服务器数据合并（用于初始化或同步）
   */
  const mergeFromServer = (serverItems: Array<{
    workflow_item_key: string
    implemented: boolean
    runs_implemented?: number
    modified_at: string
  }>): void => {
    let hasChanges = false
    
    serverItems.forEach(serverItem => {
      const localItem = implementations.value[serverItem.workflow_item_key]
      const serverTime = new Date(serverItem.modified_at).getTime()
      
      if (!localItem) {
        // 本地没有，使用服务器数据
        implementations.value[serverItem.workflow_item_key] = {
          implemented: serverItem.implemented,
          runsImplemented: serverItem.runs_implemented,
          modifiedAt: serverItem.modified_at,
          syncStatus: 'synced'
        }
        hasChanges = true
      } else {
        const localTime = new Date(localItem.modifiedAt).getTime()
        // 服务器数据更新，且不是 pending 状态
        if (serverTime > localTime && localItem.syncStatus !== 'pending') {
          implementations.value[serverItem.workflow_item_key] = {
            implemented: serverItem.implemented,
            runsImplemented: serverItem.runs_implemented,
            modifiedAt: serverItem.modified_at,
            syncStatus: 'synced'
          }
          hasChanges = true
        }
      }
    })
    
    if (hasChanges) {
      saveLocalState()
    }
  }

  /**
   * 获取所有待同步的变更
   */
  const getPendingChanges = (): Array<{
    workflow_item_key: string
    implemented: boolean
    runs_implemented?: number
    modified_at: string
  }> => {
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
   * 清理旧数据（30天前）
   */
  const cleanupOldData = (): void => {
    const pattern = new RegExp(`^${STORAGE_KEY_PREFIX}`)
    const thirtyDaysAgo = Date.now() - 30 * 24 * 60 * 60 * 1000
    
    const keysToRemove: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && pattern.test(key)) {
        try {
          const data = JSON.parse(localStorage.getItem(key) || '{}')
          if (new Date(data.lastModified).getTime() < thirtyDaysAgo) {
            keysToRemove.push(key)
          }
        } catch (e) {
          // 解析失败，删除
          keysToRemove.push(key)
        }
      }
    }
    
    keysToRemove.forEach(key => {
      localStorage.removeItem(key)
      console.log(`[WorkflowImpl] 清理旧数据: ${key}`)
    })
  }

  /**
   * 清除当前计划的所有本地数据
   */
  const clearLocalData = (): void => {
    if (!planName.value || !userName.value) return
    
    const key = buildStorageKey(userName.value, planName.value, calculationId.value)
    localStorage.removeItem(key)
    implementations.value = {}
    lastSynced.value = null
    console.log(`[WorkflowImpl] 已清除本地数据: ${key}`)
  }

  // 监听 calculationId 变化（新计算周期）
  watch(calculationId, (newId, oldId) => {
    if (newId !== oldId) {
      console.log(`[WorkflowImpl] calculationId 变化: ${oldId} -> ${newId}`)
      loadLocalState()
    }
  })

  // 监听 planName 变化
  watch(planName, (newPlan, oldPlan) => {
    if (newPlan !== oldPlan) {
      console.log(`[WorkflowImpl] planName 变化: ${oldPlan} -> ${newPlan}`)
      loadLocalState()
    }
  })

  // 初始化加载
  loadLocalState()

  return {
    // 状态
    implementations,
    lastSynced,
    lastModified,
    
    // 方法
    loadLocalState,
    saveLocalState,
    markImplemented,
    unmarkImplemented,
    toggleImplemented,
    isImplemented,
    getRunsImplemented,
    setRunsImplemented,
    addMoreImplementation,
    getPartialProgress,
    getRunsImplementedDisplay,
    hasPendingChanges,
    updateSyncStatus,
    markAllAsSynced,
    mergeFromServer,
    getPendingChanges,
    cleanupOldData,
    clearLocalData,
    
    // 工具
    getWorkflowItemKey
  }
}
