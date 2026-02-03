import { ref } from 'vue'
import { http } from '@/http'
import { ElMessage } from 'element-plus'
import type { Market, ProductBasicInfo, PlanItem } from '@/views/enterprise/types/market'
import { defaultMarketSettings } from '@/views/enterprise/types/market'
import {
  PRODUCT_BASIC_INFO_CACHE_PREFIX,
  COST_CALCULATION_ROUGH_CACHE_PREFIX,
  COST_CALCULATION_PRECISE_CACHE_PREFIX
} from '@/views/enterprise/types/market'
import { useMarketStorage } from './useMarketStorage'

/**
 * 市场数据获取 composable
 */
export function useMarketData() {
  const { saveToLocalStorage, loadFromLocalStorage } = useMarketStorage()

  // 状态
  const marketList = ref<Market[]>([])
  const productBasicInfo = ref<ProductBasicInfo[]>([])
  const costCalculationResult = ref([])
  const planList = ref<PlanItem[]>([])
  const planListLoading = ref(false)
  const basicInfoLoading = ref(false)

  // 仅获取自选市场列表，不加载其他数据
  const fetchMarketListOnly = async () => {
    try {
      const res = await http.get('/enterprise/market/list')
      const data = await res.json()
      if (data.status !== 200) {
        ElMessage.error(data.message || '获取自选市场列表失败')
        return
      }
      marketList.value = data.data || []
    } catch (e) {
      ElMessage.error('获取自选市场列表失败')
    }
  }

  // 获取产品基本信息
  const fetchProductBasicInfo = async (marketId: number, marketZone: string) => {
    basicInfoLoading.value = true

    if (!marketId) {
      productBasicInfo.value = []
      basicInfoLoading.value = false
      return
    }

    try {
      // 尝试从缓存加载
      const cacheKey = `${PRODUCT_BASIC_INFO_CACHE_PREFIX}${marketId}_${marketZone}`
      const cachedData = loadFromLocalStorage(cacheKey)

      if (cachedData && cachedData.data) {
        productBasicInfo.value = cachedData.data
        basicInfoLoading.value = false
        console.log(`市场 ${marketId} 区域 ${marketZone} 的产品基本信息从缓存加载`)
        return
      }

      // 缓存不存在或已过期，从API获取
      const res = await http.get('/enterprise/market/product_basic_info', {
        market_id: marketId,
        market_zone: marketZone
      })

      const data = await res.json()
      if (data.status !== 200) {
        ElMessage.error(data.message || '获取物品基本信息失败')
        basicInfoLoading.value = false
        return
      }

      productBasicInfo.value = data.data
      // 保存到缓存
      saveToLocalStorage(cacheKey, data.data, marketId, marketZone)
    } catch (e) {
      ElMessage.error('获取物品基本信息失败')
    }
    basicInfoLoading.value = false
  }

  // 获取粗略模式成本计算结果（从系统缓存）
  const fetchRoughCostCalculationResult = async (marketId: number, marketZone: string) => {
    try {
      // 如果计划列表为空，获取计划数据
      if (!planList.value || planList.value.length === 0) {
        await fetchPlanList()
      }

      // 尝试从本地缓存加载
      const cacheKey = `${COST_CALCULATION_ROUGH_CACHE_PREFIX}${marketId}_${marketZone}`
      const cachedData = loadFromLocalStorage(cacheKey)

      if (cachedData && cachedData.data) {
        costCalculationResult.value = cachedData.data
        console.log(`市场 ${marketId} 区域 ${marketZone} 的粗略模式成本计算结果从本地缓存加载了 ${cachedData.data.length} 条`)
        return cachedData.data
      }

      // 本地缓存不存在或已过期，从API获取
      const res = await http.post('/enterprise/market/cost_calculation/rough_result', {
        market_id: marketId
      })

      const data = await res.json()
      if (data.status === 200 && data.data) {
        costCalculationResult.value = data.data
        // 保存到本地缓存
        saveToLocalStorage(cacheKey, data.data, marketId, marketZone)
        console.log(`市场 ${marketId} 从系统缓存加载了 ${data.data.length} 条成本计算结果，已保存到本地缓存`)
        return data.data
      } else {
        costCalculationResult.value = []
        console.log(`市场 ${marketId} 系统缓存中没有成本计算结果`)
      }
    } catch (e) {
      console.error('获取粗略模式成本计算结果失败:', e)
      costCalculationResult.value = []
    }
    return null
  }

  // 尝试获取计算结果（用于缓存）
  const tryGetCostCalculationResult = async (marketId: number, settings: any) => {
    try {
      // 获取当前市场的计划名称
      const planName = settings.selectedPlanName

      if (!planName) {
        costCalculationResult.value = []
        return null
      }

      // 如果计划列表为空，获取计划数据
      if (!planList.value || planList.value.length === 0) {
        await fetchPlanList()
      }

      // 尝试从本地缓存加载
      const cacheKey = `${COST_CALCULATION_PRECISE_CACHE_PREFIX}${marketId}_${planName}`
      const cachedData = loadFromLocalStorage(cacheKey)

      if (cachedData && cachedData.data) {
        costCalculationResult.value = cachedData.data
        console.log(`市场 ${marketId} 计划 ${planName} 的精确模式成本计算结果从本地缓存加载了 ${cachedData.data.length} 条`)
        return cachedData.data
      }

      // 本地缓存不存在或已过期，先检查服务器状态
      const statusRes = await http.post('/enterprise/market/cost_calculation/status', {
        market_id: marketId
      })

      const statusData = await statusRes.json()
      if (statusData.status === 200 && statusData.data?.status === 'completed') {
        // 状态为完成，尝试获取结果
        const resultRes = await http.post('/enterprise/market/cost_calculation/result', {
          market_id: marketId
        })

        const resultData = await resultRes.json()
        if (resultData.status === 200 && resultData.data) {
          // 有缓存结果，保存到 costCalculationResult 和本地缓存
          costCalculationResult.value = resultData.data
          saveToLocalStorage(cacheKey, resultData.data, marketId, undefined, planName)
          console.log(`市场 ${marketId} 计划 ${planName} 有缓存的计算结果，已加载 ${resultData.data.length} 条记录，已保存到本地缓存`)
          return resultData.data
        }
      } else {
        // 如果没有完成的计算，清空结果
        costCalculationResult.value = []
      }
    } catch (e) {
      // 静默失败，不影响正常流程
      console.debug('获取缓存结果失败:', e)
      costCalculationResult.value = []
    }
    return null
  }

  // 获取计划列表
  const fetchPlanList = async () => {
    planListLoading.value = true
    try {
      const res = await http.post('/EVE/industry/getPlanTableData')
      const data = await res.json()
      if (data.status === 200) {
        planList.value = data.data || []
      } else {
        ElMessage.error(data.message || '获取计划列表失败')
      }
    } catch (e) {
      ElMessage.error('获取计划列表失败')
    } finally {
      planListLoading.value = false
    }
  }

  return {
    // 状态
    marketList,
    productBasicInfo,
    costCalculationResult,
    planList,
    planListLoading,
    basicInfoLoading,
    // 方法
    fetchMarketListOnly,
    fetchProductBasicInfo,
    fetchRoughCostCalculationResult,
    tryGetCostCalculationResult,
    fetchPlanList
  }
}
