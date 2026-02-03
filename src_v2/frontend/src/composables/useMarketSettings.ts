import { ref, computed, watch, type ComputedRef } from 'vue'
import type { MarketSettings, MarketVisibleColumnIds, ExtraCostMap } from '@/views/enterprise/types/market'
import { defaultMarketSettings, defaultVisibleColumnIds } from '@/views/enterprise/types/market'
import { useMarketStorage } from './useMarketStorage'
import type { PlanItem } from '@/views/enterprise/types/market'

/**
 * 市场设置管理 composable
 */
export function useMarketSettings(planList: { value: PlanItem[] }) {
  const {
    saveMarketSettings,
    loadMarketSettings,
    deleteMarketSettings,
    saveMarketColumnSettings,
    loadMarketColumnSettings,
    deleteMarketColumnSettings,
    saveMarketExtraCostSettings,
    loadMarketExtraCostSettings,
    deleteMarketExtraCostSettings
  } = useMarketStorage()

  // 状态
  const marketSettingsMap = ref<Record<number, MarketSettings>>({})
  const marketColumnSettingsMap = ref<Record<number, MarketVisibleColumnIds>>({})
  const marketExtraCostMap = ref<Record<number, ExtraCostMap>>({})

  // 加载市场设置
  const loadMarketSettingsForMarket = (marketId: number) => {
    const savedSettings = loadMarketSettings(marketId)
    if (savedSettings) {
      // 验证保存的计划是否还在计划列表中（只有在计划列表已加载时才验证）
      if (savedSettings.selectedPlanName && planList.value.length > 0) {
        const planExists = planList.value.some(plan => plan.plan_name === savedSettings.selectedPlanName)
        if (!planExists) {
          // 如果计划不存在，清除计划选择
          savedSettings.selectedPlanName = ''
        }
      }
      // 合并默认设置，确保新添加的字段（如 defaultProfitRate, costCalculationMode）有默认值
      marketSettingsMap.value[marketId] = { ...defaultMarketSettings, ...savedSettings }
      // 如果保存的设置中没有 costCalculationMode，使用默认值
      if (!marketSettingsMap.value[marketId].costCalculationMode) {
        marketSettingsMap.value[marketId].costCalculationMode = 'rough'
      }
    } else {
      // 如果没有保存的设置，使用默认值
      marketSettingsMap.value[marketId] = { ...defaultMarketSettings }
    }
  }

  // 加载所有市场的本地设置
  const loadMarketSettingsForAllMarkets = (marketList: any[]) => {
    marketList.forEach((market) => {
      loadMarketSettingsForMarket(market.id)
    })
  }

  // 加载单个市场的额外成本
  const loadMarketExtraCostForMarket = (marketId: number) => {
    const savedExtraCost = loadMarketExtraCostSettings(marketId)
    if (savedExtraCost) {
      marketExtraCostMap.value[marketId] = savedExtraCost
    } else {
      marketExtraCostMap.value[marketId] = {}
    }
  }

  // 加载所有市场的额外成本
  const loadMarketExtraCostForAllMarkets = (marketList: any[]) => {
    marketList.forEach((market) => {
      loadMarketExtraCostForMarket(market.id)
    })
  }

  // 加载所有市场的列设置
  const loadMarketColumnSettingsForAllMarkets = (marketList: any[]) => {
    marketList.forEach((market) => {
      const savedColumns = loadMarketColumnSettings(market.id)
      if (savedColumns && savedColumns.length > 0) {
        // 只保留合法列 ID，尊重用户隐藏选择；确保操作列存在
        const filtered = savedColumns.filter(id => defaultVisibleColumnIds.includes(id))
        if (!filtered.includes('actions')) {
          filtered.push('actions')
        }
        marketColumnSettingsMap.value[market.id] = filtered
      } else {
        // 没有任何保存记录时，首次使用默认列
        marketColumnSettingsMap.value[market.id] = [...defaultVisibleColumnIds]
      }
    })
  }

  // 获取当前市场的设置（带默认值）
  const getCurrentMarketSettings = (currentMarketId: number | null) => {
    if (!currentMarketId) {
      return defaultMarketSettings
    }
    return marketSettingsMap.value[currentMarketId] || defaultMarketSettings
  }

  // 获取当前市场的列显示设置
  const getCurrentVisibleColumnIds = (currentMarketId: number | null): MarketVisibleColumnIds => {
    if (!currentMarketId) {
      return defaultVisibleColumnIds
    }
    const saved = marketColumnSettingsMap.value[currentMarketId]
    // 如果当前市场还没有专门的列配置，就用默认列
    if (!saved || saved.length === 0) {
      return defaultVisibleColumnIds
    }
    // 直接返回已保存配置，尊重用户的显示/隐藏选择
    return saved
  }

  // 获取当前市场的额外成本映射
  const getCurrentMarketExtraCostMap = (currentMarketId: number | null): ExtraCostMap => {
    if (!currentMarketId) {
      return {}
    }
    return marketExtraCostMap.value[currentMarketId] || {}
  }

  // 更新当前市场某个物品的额外成本
  const handleUpdateExtraCost = (currentMarketId: number | null, typeId: number, value: number) => {
    if (!currentMarketId) {
      return
    }
    const marketId = currentMarketId
    if (!marketExtraCostMap.value[marketId]) {
      marketExtraCostMap.value[marketId] = {}
    }
    // 确保为数字，NaN 时按 0 处理
    const numericValue = isNaN(value) ? 0 : value
    marketExtraCostMap.value[marketId][typeId] = numericValue
    saveMarketExtraCostSettings(marketId, marketExtraCostMap.value[marketId])
  }

  // 创建计算属性：当前市场的各个设置项（用于v-model绑定）
  const createMarketSettingComputed = (currentMarketId: ComputedRef<number | null>) => {
    const selectedPlanName = computed({
      get: () => {
        const settings = getCurrentMarketSettings(currentMarketId.value)
        return settings.selectedPlanName
      },
      set: (value: string) => {
        if (currentMarketId.value) {
          if (!marketSettingsMap.value[currentMarketId.value]) {
            marketSettingsMap.value[currentMarketId.value] = { ...defaultMarketSettings }
          }
          marketSettingsMap.value[currentMarketId.value].selectedPlanName = value
        }
      }
    })

    const costCalculationPriceBase = computed({
      get: () => {
        const settings = getCurrentMarketSettings(currentMarketId.value)
        return settings.costCalculationPriceBase
      },
      set: (value: 'buy' | 'mid' | 'sell') => {
        if (currentMarketId.value) {
          if (!marketSettingsMap.value[currentMarketId.value]) {
            marketSettingsMap.value[currentMarketId.value] = { ...defaultMarketSettings }
          }
          marketSettingsMap.value[currentMarketId.value].costCalculationPriceBase = value
        }
      }
    })

    const costCalculationSaleTax = computed({
      get: () => {
        const settings = getCurrentMarketSettings(currentMarketId.value)
        return settings.costCalculationSaleTax
      },
      set: (value: number) => {
        if (currentMarketId.value) {
          if (!marketSettingsMap.value[currentMarketId.value]) {
            marketSettingsMap.value[currentMarketId.value] = { ...defaultMarketSettings }
          }
          marketSettingsMap.value[currentMarketId.value].costCalculationSaleTax = value
        }
      }
    })

    const costCalculationMediatorTax = computed({
      get: () => {
        const settings = getCurrentMarketSettings(currentMarketId.value)
        return settings.costCalculationMediatorTax
      },
      set: (value: number) => {
        if (currentMarketId.value) {
          if (!marketSettingsMap.value[currentMarketId.value]) {
            marketSettingsMap.value[currentMarketId.value] = { ...defaultMarketSettings }
          }
          marketSettingsMap.value[currentMarketId.value].costCalculationMediatorTax = value
        }
      }
    })

    const selectedMarketZone = computed({
      get: () => {
        const settings = getCurrentMarketSettings(currentMarketId.value)
        return settings.selectedMarketZone || 'jita'
      },
      set: (value: string) => {
        if (currentMarketId.value) {
          if (!marketSettingsMap.value[currentMarketId.value]) {
            marketSettingsMap.value[currentMarketId.value] = { ...defaultMarketSettings }
          }
          marketSettingsMap.value[currentMarketId.value].selectedMarketZone = value
        }
      }
    })

    const defaultProfitRate = computed({
      get: () => {
        const settings = getCurrentMarketSettings(currentMarketId.value)
        return settings.defaultProfitRate
      },
      set: (value: number) => {
        if (currentMarketId.value) {
          if (!marketSettingsMap.value[currentMarketId.value]) {
            marketSettingsMap.value[currentMarketId.value] = { ...defaultMarketSettings }
          }
          marketSettingsMap.value[currentMarketId.value].defaultProfitRate = value
        }
      }
    })

    const costCalculationMode = computed({
      get: () => {
        const settings = getCurrentMarketSettings(currentMarketId.value)
        return settings.costCalculationMode || 'rough'
      },
      set: (value: 'rough' | 'precise') => {
        if (currentMarketId.value) {
          if (!marketSettingsMap.value[currentMarketId.value]) {
            marketSettingsMap.value[currentMarketId.value] = { ...defaultMarketSettings }
          }
          marketSettingsMap.value[currentMarketId.value].costCalculationMode = value
        }
      }
    })

    const monthlyCapacity = computed({
      get: () => {
        const settings = getCurrentMarketSettings(currentMarketId.value)
        return settings.monthlyCapacity ?? defaultMarketSettings.monthlyCapacity ?? 50000000000
      },
      set: (value: number) => {
        if (currentMarketId.value) {
          if (!marketSettingsMap.value[currentMarketId.value]) {
            marketSettingsMap.value[currentMarketId.value] = { ...defaultMarketSettings }
          }
          marketSettingsMap.value[currentMarketId.value].monthlyCapacity = value
        }
      }
    })

    const deliveryCostPerVolume = computed({
      get: () => {
        const settings = getCurrentMarketSettings(currentMarketId.value)
        return settings.deliveryCostPerVolume ?? defaultMarketSettings.deliveryCostPerVolume ?? 0
      },
      set: (value: number) => {
        if (currentMarketId.value) {
          if (!marketSettingsMap.value[currentMarketId.value]) {
            marketSettingsMap.value[currentMarketId.value] = { ...defaultMarketSettings }
          }
          marketSettingsMap.value[currentMarketId.value].deliveryCostPerVolume = value
        }
      }
    })

    const deliveryCostPercentage = computed({
      get: () => {
        const settings = getCurrentMarketSettings(currentMarketId.value)
        return settings.deliveryCostPercentage ?? defaultMarketSettings.deliveryCostPercentage ?? 0
      },
      set: (value: number) => {
        if (currentMarketId.value) {
          if (!marketSettingsMap.value[currentMarketId.value]) {
            marketSettingsMap.value[currentMarketId.value] = { ...defaultMarketSettings }
          }
          marketSettingsMap.value[currentMarketId.value].deliveryCostPercentage = value
        }
      }
    })

    const currentDefaultProfitRate = computed(() => {
      if (!currentMarketId.value) {
        return defaultMarketSettings.defaultProfitRate
      }
      return getCurrentMarketSettings(currentMarketId.value).defaultProfitRate
    })

    return {
      selectedPlanName,
      costCalculationPriceBase,
      costCalculationSaleTax,
      costCalculationMediatorTax,
      selectedMarketZone,
      defaultProfitRate,
      costCalculationMode,
      monthlyCapacity,
      deliveryCostPerVolume,
      deliveryCostPercentage,
      currentDefaultProfitRate
    }
  }

  // 监听市场设置变化，自动保存到本地存储
  const watchMarketSettings = () => {
    watch(
      marketSettingsMap,
      (newMap) => {
        // 遍历所有市场的设置，保存到本地存储
        Object.keys(newMap).forEach((marketIdStr) => {
          const marketId = Number(marketIdStr)
          const settings = newMap[marketId]
          if (settings) {
            saveMarketSettings(marketId, settings)
          }
        })
      },
      { deep: true }
    )
  }

  // 清理市场设置
  const cleanupMarketSettings = (marketId: number) => {
    deleteMarketSettings(marketId)
    deleteMarketColumnSettings(marketId)
    deleteMarketExtraCostSettings(marketId)
    delete marketSettingsMap.value[marketId]
    delete marketColumnSettingsMap.value[marketId]
    delete marketExtraCostMap.value[marketId]
  }

  return {
    // 状态
    marketSettingsMap,
    marketColumnSettingsMap,
    marketExtraCostMap,
    // 方法
    loadMarketSettingsForMarket,
    loadMarketSettingsForAllMarkets,
    loadMarketExtraCostForMarket,
    loadMarketExtraCostForAllMarkets,
    loadMarketColumnSettingsForAllMarkets,
    getCurrentMarketSettings,
    getCurrentVisibleColumnIds,
    getCurrentMarketExtraCostMap,
    handleUpdateExtraCost,
    createMarketSettingComputed,
    watchMarketSettings,
    cleanupMarketSettings
  }
}
