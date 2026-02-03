import type { MarketSettings, MarketVisibleColumnIds, ExtraCostMap, CacheData } from '@/views/enterprise/types/market'
import {
  MARKET_SETTINGS_STORAGE_KEY_PREFIX,
  MARKET_COLUMNS_STORAGE_KEY_PREFIX,
  MARKET_EXTRA_COST_STORAGE_KEY_PREFIX,
  PRODUCT_BASIC_INFO_CACHE_PREFIX,
  COST_CALCULATION_ROUGH_CACHE_PREFIX,
  COST_CALCULATION_PRECISE_CACHE_PREFIX
} from '@/views/enterprise/types/market'

/**
 * 市场本地存储管理 composable
 */
export function useMarketStorage() {
  // ======================= 市场设置存储 =====================
  
  // 保存市场设置到本地存储
  const saveMarketSettings = (marketId: number, settings: MarketSettings) => {
    try {
      const key = `${MARKET_SETTINGS_STORAGE_KEY_PREFIX}${marketId}`
      localStorage.setItem(key, JSON.stringify(settings))
      console.log(`市场 ${marketId} 的设置已保存到本地`)
    } catch (error) {
      console.error('保存市场设置失败:', error)
    }
  }

  // 从本地存储加载市场设置
  const loadMarketSettings = (marketId: number): MarketSettings | null => {
    try {
      const key = `${MARKET_SETTINGS_STORAGE_KEY_PREFIX}${marketId}`
      const data = localStorage.getItem(key)
      if (data) {
        const parsed = JSON.parse(data) as MarketSettings
        console.log(`从本地加载市场 ${marketId} 的设置`)
        return parsed
      }
    } catch (error) {
      console.error('加载市场设置失败:', error)
    }
    return null
  }

  // 删除市场设置
  const deleteMarketSettings = (marketId: number) => {
    try {
      const key = `${MARKET_SETTINGS_STORAGE_KEY_PREFIX}${marketId}`
      localStorage.removeItem(key)
      console.log(`市场 ${marketId} 的设置已删除`)
    } catch (error) {
      console.error('删除市场设置失败:', error)
    }
  }

  // ======================= 列设置存储 =====================

  // 保存市场列设置到本地存储
  const saveMarketColumnSettings = (marketId: number, visibleColumns: MarketVisibleColumnIds) => {
    try {
      const key = `${MARKET_COLUMNS_STORAGE_KEY_PREFIX}${marketId}`
      localStorage.setItem(key, JSON.stringify(visibleColumns))
      console.log(`市场 ${marketId} 的列设置已保存到本地`)
    } catch (error) {
      console.error('保存市场列设置失败:', error)
    }
  }

  // 从本地存储加载市场列设置
  const loadMarketColumnSettings = (marketId: number): MarketVisibleColumnIds | null => {
    try {
      const key = `${MARKET_COLUMNS_STORAGE_KEY_PREFIX}${marketId}`
      const data = localStorage.getItem(key)
      if (data) {
        const parsed = JSON.parse(data) as MarketVisibleColumnIds
        console.log(`从本地加载市场 ${marketId} 的列设置`)
        return parsed
      }
    } catch (error) {
      console.error('加载市场列设置失败:', error)
    }
    return null
  }

  // 删除市场列设置
  const deleteMarketColumnSettings = (marketId: number) => {
    try {
      const key = `${MARKET_COLUMNS_STORAGE_KEY_PREFIX}${marketId}`
      localStorage.removeItem(key)
      console.log(`市场 ${marketId} 的列设置已删除`)
    } catch (error) {
      console.error('删除市场列设置失败:', error)
    }
  }

  // ======================= 额外成本存储 =====================

  // 保存市场额外成本到本地存储
  const saveMarketExtraCostSettings = (marketId: number, extraCostMap: ExtraCostMap) => {
    try {
      const key = `${MARKET_EXTRA_COST_STORAGE_KEY_PREFIX}${marketId}`
      localStorage.setItem(key, JSON.stringify(extraCostMap))
      console.log(`市场 ${marketId} 的额外成本已保存到本地`)
    } catch (error) {
      console.error('保存市场额外成本失败:', error)
    }
  }

  // 从本地存储加载市场额外成本
  const loadMarketExtraCostSettings = (marketId: number): ExtraCostMap | null => {
    try {
      const key = `${MARKET_EXTRA_COST_STORAGE_KEY_PREFIX}${marketId}`
      const data = localStorage.getItem(key)
      if (data) {
        const parsed = JSON.parse(data) as ExtraCostMap
        console.log(`从本地加载市场 ${marketId} 的额外成本`)
        return parsed
      }
    } catch (error) {
      console.error('加载市场额外成本失败:', error)
    }
    return null
  }

  // 删除市场额外成本
  const deleteMarketExtraCostSettings = (marketId: number) => {
    try {
      const key = `${MARKET_EXTRA_COST_STORAGE_KEY_PREFIX}${marketId}`
      localStorage.removeItem(key)
      console.log(`市场 ${marketId} 的额外成本已删除`)
    } catch (error) {
      console.error('删除市场额外成本失败:', error)
    }
  }

  // ======================= 数据缓存工具函数 =====================
  
  // 计算第二天凌晨3点的时间戳
  const getNextDay3AMTimestamp = (): number => {
    const now = new Date()
    const tomorrow = new Date(now)
    tomorrow.setDate(tomorrow.getDate() + 1)
    tomorrow.setHours(3, 0, 0, 0)
    return tomorrow.getTime()
  }

  // 检查缓存是否有效
  const isCacheValid = (cacheData: CacheData | null): boolean => {
    if (!cacheData) {
      return false
    }
    const now = Date.now()
    return cacheData.expireTime > now
  }

  // 保存数据到本地存储（包含过期时间）
  const saveToLocalStorage = (key: string, data: any, marketId: number, marketZone?: string, planName?: string) => {
    try {
      const cacheData: CacheData = {
        data,
        expireTime: getNextDay3AMTimestamp(),
        marketId,
        marketZone,
        planName
      }
      localStorage.setItem(key, JSON.stringify(cacheData))
      console.log(`缓存已保存: ${key}`)
    } catch (error) {
      console.error(`保存缓存失败 ${key}:`, error)
    }
  }

  // 从本地存储加载数据（检查过期时间）
  const loadFromLocalStorage = (key: string): CacheData | null => {
    try {
      const data = localStorage.getItem(key)
      if (data) {
        const cacheData = JSON.parse(data) as CacheData
        if (isCacheValid(cacheData)) {
          console.log(`从缓存加载: ${key}`)
          return cacheData
        } else {
          // 缓存已过期，删除
          localStorage.removeItem(key)
          console.log(`缓存已过期，已删除: ${key}`)
        }
      }
    } catch (error) {
      console.error(`加载缓存失败 ${key}:`, error)
    }
    return null
  }

  // 清除指定市场的所有缓存
  const clearMarketCache = (marketId: number) => {
    try {
      // 清除产品基本信息缓存（需要遍历所有可能的 marketZone）
      const marketZones = ['jita', 'frt']
      marketZones.forEach(zone => {
        const key = `${PRODUCT_BASIC_INFO_CACHE_PREFIX}${marketId}_${zone}`
        localStorage.removeItem(key)
      })

      // 清除粗略模式成本计算缓存
      marketZones.forEach(zone => {
        const key = `${COST_CALCULATION_ROUGH_CACHE_PREFIX}${marketId}_${zone}`
        localStorage.removeItem(key)
      })

      // 清除精确模式成本计算缓存（需要遍历所有可能的 planName）
      // 由于 planName 很多，我们使用前缀匹配来删除
      const keysToRemove: string[] = []
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i)
        if (key && key.startsWith(`${COST_CALCULATION_PRECISE_CACHE_PREFIX}${marketId}_`)) {
          keysToRemove.push(key)
        }
      }
      keysToRemove.forEach(key => localStorage.removeItem(key))

      console.log(`已清除市场 ${marketId} 的所有缓存`)
    } catch (error) {
      console.error(`清除市场缓存失败 ${marketId}:`, error)
    }
  }

  // 清除指定市场和区域的缓存
  const clearMarketZoneCache = (marketId: number, marketZone: string) => {
    try {
      const productKey = `${PRODUCT_BASIC_INFO_CACHE_PREFIX}${marketId}_${marketZone}`
      const roughKey = `${COST_CALCULATION_ROUGH_CACHE_PREFIX}${marketId}_${marketZone}`
      localStorage.removeItem(productKey)
      localStorage.removeItem(roughKey)
      console.log(`已清除市场 ${marketId} 区域 ${marketZone} 的缓存`)
    } catch (error) {
      console.error(`清除市场区域缓存失败 ${marketId}_${marketZone}:`, error)
    }
  }

  // 清除指定市场和计划的缓存
  const clearMarketPlanCache = (marketId: number, planName: string) => {
    try {
      const key = `${COST_CALCULATION_PRECISE_CACHE_PREFIX}${marketId}_${planName}`
      localStorage.removeItem(key)
      console.log(`已清除市场 ${marketId} 计划 ${planName} 的缓存`)
    } catch (error) {
      console.error(`清除市场计划缓存失败 ${marketId}_${planName}:`, error)
    }
  }

  return {
    // 市场设置
    saveMarketSettings,
    loadMarketSettings,
    deleteMarketSettings,
    // 列设置
    saveMarketColumnSettings,
    loadMarketColumnSettings,
    deleteMarketColumnSettings,
    // 额外成本
    saveMarketExtraCostSettings,
    loadMarketExtraCostSettings,
    deleteMarketExtraCostSettings,
    // 缓存管理
    saveToLocalStorage,
    loadFromLocalStorage,
    clearMarketCache,
    clearMarketZoneCache,
    clearMarketPlanCache
  }
}
