import { ref, computed, watch } from 'vue'

const STORAGE_KEY = 'kahuna_ore_blacklist'

export interface BlacklistEntry {
  type_id: number
  name_zh: string
}

/**
 * 矿石黑名单管理 composable
 * 存储于 localStorage，所有计划共用
 */
export function useOreBlacklist() {
  const blacklist = ref<BlacklistEntry[]>(loadFromStorage())

  function loadFromStorage(): BlacklistEntry[] {
    try {
      const data = localStorage.getItem(STORAGE_KEY)
      return data ? JSON.parse(data) : []
    } catch {
      return []
    }
  }

  function saveToStorage() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(blacklist.value))
    } catch (e) {
      console.error('保存矿石黑名单失败:', e)
    }
  }

  // 监听变化自动保存
  watch(blacklist, saveToStorage, { deep: true })

  /** 黑名单 type_id 集合（用于快速查询） */
  const blacklistedIds = computed(() =>
    new Set(blacklist.value.map(e => e.type_id))
  )

  /** 黑名单 type_id 数组（用于 API 传参） */
  const blacklistedIdArray = computed(() =>
    blacklist.value.map(e => e.type_id)
  )

  /** 添加到黑名单 */
  function addToBlacklist(typeId: number, nameZh: string) {
    if (!blacklistedIds.value.has(typeId)) {
      blacklist.value.push({ type_id: typeId, name_zh: nameZh })
    }
  }

  /** 从黑名单移除 */
  function removeFromBlacklist(typeId: number) {
    blacklist.value = blacklist.value.filter(e => e.type_id !== typeId)
  }

  /** 检查是否在黑名单中 */
  function isBlacklisted(typeId: number): boolean {
    return blacklistedIds.value.has(typeId)
  }

  return {
    blacklist,
    blacklistedIds,
    blacklistedIdArray,
    addToBlacklist,
    removeFromBlacklist,
    isBlacklisted,
  }
}
