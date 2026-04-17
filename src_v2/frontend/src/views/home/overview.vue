<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { Refresh, Filter, Money, Wallet, ShoppingCart, Timer, Star, Box } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { http } from '@/http'
import { handleApiResponse } from '@/utils/apiResponse'
import { useTransition } from '@vueuse/core'
import { getChartThemeColors, themedTooltip, onThemeTokenChange } from '@/utils/echartsTheme'

// 数据接口
interface OverviewData {
  totalValue?: number          // 总价值（可选，历史记录可能没有）
  walletValue: number | Record<string, number>  // 钱包总价值（可能是数字或对象）
  orderValue: number | Record<string, number>  // 订单总价值（可能是数字或对象）
  runningProcessValue: number  // 运行中流程价值
  markedAssetValue: number     // 标记资产价值
  unmarkedAssetValue: number   // 非标记资产价值
}

// Overview API 响应接口
interface OverviewResponse {
  today: OverviewData
  last_note: OverviewData | null  // 保持向后兼容
  last_note_1d: OverviewData | null  // 1天前的数据
  last_note_7d: OverviewData | null  // 7天前的数据
  last_note_30d: OverviewData | null  // 30天前的数据
  earliest_note: OverviewData | null  // 最早的数据
}

// API 响应接口
interface ApiResponse<T> {
  status: number
  data: T
}

// 静态数据函数
const getOverviewData = (): OverviewData => {
  return {
    totalValue: 1500000000,
    walletValue: 500000000,
    orderValue: 0,
    runningProcessValue: 300000000,
    markedAssetValue: 400000000,
    unmarkedAssetValue: 300000000
  }
}

// 角色选项接口
interface CharacterOption {
  value: number  // character_id
  label: string  // name
}

// 资产拉取任务选项接口
interface AssetMissionOption {
  value: string  // "{subject_type}_{subject_id}" 格式，如 "character_123456" 或 "corp_789012"
  label: string  // subject_name (character_name 或 corpname)
}

// 响应式数据
const overviewData = ref<OverviewData | null>(getOverviewData())
const lastNoteData = ref<OverviewData | null>(null)  // 上一次历史记录（保持向后兼容）
const lastNote1d = ref<OverviewData | null>(null)  // 1天前的数据
const lastNote7d = ref<OverviewData | null>(null)  // 7天前的数据
const lastNote30d = ref<OverviewData | null>(null)  // 30天前的数据
const earliestNote = ref<OverviewData | null>(null)  // 最早的数据
const INCLUDE_UNMARKED_STORAGE_KEY = 'overview_include_unmarked_assets'
const TIME_RANGE_STORAGE_KEY = 'overview_time_range'
const includeMarkedAssets = ref(true)  // 考虑被标记资产开关
const selectedTimeRange = ref<'1d' | '7d' | '30d'>('1d')  // 时间范围选择：一天、本周、本月
const loading = ref(false)

// 角色筛选相关
const STORAGE_KEY = 'overview_character_filter_ids'
const characterOptions = ref<CharacterOption[]>([])
const selectedCharacterIdsRaw = ref<number[]>([])
const filterDialogVisible = ref(false)
const characterIdToNameMap = ref<Record<number, string>>({})
const hasRestoredFromStorage = ref(false) // 标记是否已从本地存储恢复

// 资产筛选相关
const ASSET_STORAGE_KEY = 'overview_asset_mission_filter_keys'
const assetMissionOptions = ref<AssetMissionOption[]>([])
const selectedAssetMissionKeysRaw = ref<string[]>([])
const assetFilterDialogVisible = ref(false)
const hasRestoredAssetFilterFromStorage = ref(false) // 标记是否已从本地存储恢复资产筛选

// 物品搜索相关
interface AssetSearchResult {
  asset: {
    type_name: string
    quantity: number
    location_flag: string
  }
  container: {
    item_id: number
  }
  structure: {
    structure_name: string
  }
}

interface AssetSearchForm {
  item_name: string
  data: AssetSearchResult[]
}

const assetSearchDialogVisible = ref(false)
const assetSearchForm = ref<AssetSearchForm>({
  item_name: '',
  data: []
})
const assetSearchLoading = ref(false)

// 钱包详情弹窗相关
interface CharacterWalletDetail {
  characterName: string
  walletValue: number
}

const walletDetailDialogVisible = ref(false)
const walletDetailList = ref<CharacterWalletDetail[]>([])
const walletDetailTotal = ref(0)

// 订单详情弹窗相关
interface OrderDetail {
  character_name: string
  type_name: string
  order_type: string
  location_name: string
  volume_total: number
  volume_remain: number
  completion_percent: number
  remaining_value: number
  remaining_time_minutes: number | null
  price: number
  region_id: number | null
  order_id: number | null
  is_buy_order: boolean
}

const orderDetailDialogVisible = ref(false)
const orderDetailList = ref<OrderDetail[]>([])
const orderDetailLoading = ref(false)
const orderDetailTotal = ref(0)

// 运行中任务详情弹窗相关
interface RunningJobDetail {
  job_type: string
  product_type_id: number
  product_name: string
  product_name_zh: string
  runs: number
  product_quantity_per_run: number
  total_quantity: number
  progress_percent: number
  cost: number
  installer_name: string
  value: number
  start_date: string
  end_date: string
}

interface RunningJobSummary {
  product_type_id: number
  product_name: string
  product_name_zh: string
  total_quantity: number
  total_value: number
}

interface CharacterSummary {
  character_id: number
  character_name: string
  manufacturing_running_count: number
  manufacturing_completed_count: number
  reaction_running_count: number
  reaction_completed_count: number
}

const runningJobsDialogVisible = ref(false)
const runningJobsViewMode = ref<'detail' | 'summary' | 'character'>('detail')
const runningJobsDetailList = ref<RunningJobDetail[]>([])
const runningJobsSummaryList = ref<RunningJobSummary[]>([])
const runningJobsCharacterSummaryList = ref<CharacterSummary[]>([])
const runningJobsLoading = ref(false)

// 从本地存储加载"考虑非标记资产"设置
const loadIncludeUnmarkedFromStorage = (): boolean => {
  try {
    const stored = localStorage.getItem(INCLUDE_UNMARKED_STORAGE_KEY)
    if (stored !== null) {
      return JSON.parse(stored) === true
    }
  } catch (error) {
    console.error('加载"考虑非标记资产"设置失败:', error)
  }
  return true // 默认值
}

// 保存"考虑非标记资产"设置到本地存储
const saveIncludeUnmarkedToStorage = (value: boolean) => {
  try {
    localStorage.setItem(INCLUDE_UNMARKED_STORAGE_KEY, JSON.stringify(value))
  } catch (error) {
    console.error('保存"考虑非标记资产"设置失败:', error)
  }
}

// 从本地存储加载时间范围选择
const loadTimeRangeFromStorage = (): '1d' | '7d' | '30d' => {
  try {
    const stored = localStorage.getItem(TIME_RANGE_STORAGE_KEY)
    if (stored && (stored === '1d' || stored === '7d' || stored === '30d')) {
      return stored as '1d' | '7d' | '30d'
    }
  } catch (error) {
    console.error('加载时间范围选择失败:', error)
  }
  return '1d' // 默认值
}

// 保存时间范围选择到本地存储
const saveTimeRangeToStorage = (value: '1d' | '7d' | '30d') => {
  try {
    localStorage.setItem(TIME_RANGE_STORAGE_KEY, value)
  } catch (error) {
    console.error('保存时间范围选择失败:', error)
  }
}

// 从本地存储加载筛选设置
const loadFilterFromStorage = (): number[] => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const ids = JSON.parse(stored)
      if (Array.isArray(ids) && ids.every(id => typeof id === 'number')) {
        return ids
      }
    }
  } catch (error) {
    console.error('加载筛选设置失败:', error)
  }
  return []
}

// 保存筛选设置到本地存储
const saveFilterToStorage = (ids: number[]) => {
  try {
    if (ids.length > 0) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  } catch (error) {
    console.error('保存筛选设置失败:', error)
  }
}

// 确保 selectedCharacterIds 始终只包含有效的选项值
const selectedCharacterIds = computed({
  get: () => {
    const validIds = new Set(characterOptions.value.map(opt => opt.value))
    return selectedCharacterIdsRaw.value.filter(id => validIds.has(id))
  },
  set: (val: number[]) => {
    const validIds = new Set(characterOptions.value.map(opt => opt.value))
    selectedCharacterIdsRaw.value = val.filter(id => validIds.has(id))
  }
})

// 监控 characterOptions 变化，清理无效的选择
watch(characterOptions, () => {
  const validIds = new Set(characterOptions.value.map(opt => opt.value))
  selectedCharacterIdsRaw.value = selectedCharacterIdsRaw.value.filter(id => validIds.has(id))
}, { deep: true })

// 监控 selectedCharacterIdsRaw 变化，自动保存到本地存储
watch(selectedCharacterIdsRaw, (newIds) => {
  saveFilterToStorage(newIds)
}, { deep: true })

// 从本地存储加载资产筛选设置
const loadAssetFilterFromStorage = (): string[] => {
  try {
    const stored = localStorage.getItem(ASSET_STORAGE_KEY)
    if (stored) {
      const keys = JSON.parse(stored)
      if (Array.isArray(keys) && keys.every(key => typeof key === 'string')) {
        return keys
      }
    }
  } catch (error) {
    console.error('加载资产筛选设置失败:', error)
  }
  return []
}

// 保存资产筛选设置到本地存储
const saveAssetFilterToStorage = (keys: string[]) => {
  try {
    if (keys.length > 0) {
      localStorage.setItem(ASSET_STORAGE_KEY, JSON.stringify(keys))
    } else {
      localStorage.removeItem(ASSET_STORAGE_KEY)
    }
  } catch (error) {
    console.error('保存资产筛选设置失败:', error)
  }
}

// 确保 selectedAssetMissionKeys 始终只包含有效的选项值
const selectedAssetMissionKeys = computed({
  get: () => {
    const validKeys = new Set(assetMissionOptions.value.map(opt => opt.value))
    return selectedAssetMissionKeysRaw.value.filter(key => validKeys.has(key))
  },
  set: (val: string[]) => {
    const validKeys = new Set(assetMissionOptions.value.map(opt => opt.value))
    selectedAssetMissionKeysRaw.value = val.filter(key => validKeys.has(key))
  }
})

// 监控 assetMissionOptions 变化，清理无效的选择
watch(assetMissionOptions, () => {
  const validKeys = new Set(assetMissionOptions.value.map(opt => opt.value))
  selectedAssetMissionKeysRaw.value = selectedAssetMissionKeysRaw.value.filter(key => validKeys.has(key))
}, { deep: true })

// 监控 selectedAssetMissionKeysRaw 变化，自动保存到本地存储
watch(selectedAssetMissionKeysRaw, (newKeys) => {
  saveAssetFilterToStorage(newKeys)
}, { deep: true })

// 判断是否为空数据
const isEmpty = computed(() => overviewData.value === null)

// 图表引用
const pieChartRef = ref<HTMLElement>()
let pieChartInstance: echarts.ECharts | null = null
let cleanupThemeWatcher: (() => void) | null = null

// 格式化数字（千分位）
const formatNumber = (value: number): string => {
  if (value === null || value === undefined || isNaN(value)) {
    return '0'
  }
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

// 格式化剩余时间（分钟）
const formatRemainingTime = (minutes: number | null): string => {
  if (minutes === null || minutes === undefined) {
    return '未知'
  }
  if (minutes < 0) {
    return '已过期'
  }
  if (minutes === 0) {
    return '即将过期'
  }

  const days = Math.floor(minutes / (24 * 60))
  const hours = Math.floor((minutes % (24 * 60)) / 60)
  const mins = minutes % 60

  if (days > 0) {
    return `${days}天${hours}小时${mins}分钟`
  } else if (hours > 0) {
    return `${hours}小时${mins}分钟`
  } else {
    return `${mins}分钟`
  }
}

// 获取剩余时间的样式
const getRemainingTimeStyle = (minutes: number | null): string => {
  if (minutes === null || minutes === undefined) {
    return 'color: #909399;'
  }
  if (minutes < 60) {
    // 少于1小时，显示红色警告
    return 'color: #f56c6c; font-weight: 600;'
  } else if (minutes < 24 * 60) {
    // 少于1天，显示橙色
    return 'color: #e6a23c; font-weight: 500;'
  } else {
    // 大于1天，显示正常颜色
    return 'color: #606266;'
  }
}

// 获取进度条颜色
const getProgressColor = (percentage: number): string => {
  if (percentage >= 90) return '#67c23a'
  if (percentage >= 70) return '#e6a23c'
  if (percentage >= 50) return '#f56c6c'
  return '#909399'
}

// 格式化变化值
const formatChange = (change: ChangeData): string => {
  if (!change.hasChange) return ''
  const sign = change.diff >= 0 ? '+' : ''
  const diffStr = formatNumber(change.diff)
  if (change.percent !== null && !isFinite(change.percent)) {
    return `${sign}${diffStr} ISK`
  }
  const percentStr = change.percent !== null ? ` (${sign}${change.percent.toFixed(2)}%)` : ''
  return `${sign}${diffStr} ISK${percentStr}`
}

// 获取变化值的颜色类
const getChangeColorClass = (change: ChangeData): string => {
  if (!change.hasChange) return ''
  if (change.diff > 0) return 'change-positive'
  if (change.diff < 0) return 'change-negative'
  return ''
}

// 辅助函数：将值转换为数字（处理对象或数字）
const getNumericValue = (value: number | Record<string, number> | undefined): number => {
  if (value === undefined || value === null) return 0
  if (typeof value === 'number') return value
  if (typeof value === 'object') {
    return Object.values(value).reduce((sum, v) => sum + (typeof v === 'number' ? v : 0), 0)
  }
  return 0
}

// 展示数据
const displayData = computed(() => {
  if (!overviewData.value) {
    return {
      totalValue: 0,
      walletValue: 0,
      orderValue: 0,
      runningProcessValue: 0,
      markedAssetValue: 0,
      unmarkedAssetValue: 0
    }
  }

  const walletValue = getNumericValue(overviewData.value.walletValue)
  const orderValue = getNumericValue(overviewData.value.orderValue)
  const totalValue = walletValue + orderValue + overviewData.value.runningProcessValue + overviewData.value.markedAssetValue + overviewData.value.unmarkedAssetValue
  return {
    totalValue: totalValue,
    walletValue: walletValue,
    orderValue: orderValue,
    runningProcessValue: overviewData.value.runningProcessValue,
    markedAssetValue: overviewData.value.markedAssetValue,
    unmarkedAssetValue: overviewData.value.unmarkedAssetValue
  }
})

// 根据选择的时间范围获取对应的历史数据
const getSelectedHistoryData = (): OverviewData | null => {
  switch (selectedTimeRange.value) {
    case '1d':
      return lastNote1d.value || earliestNote.value
    case '7d':
      return lastNote7d.value || earliestNote.value
    case '30d':
      return lastNote30d.value || earliestNote.value
    default:
      return lastNote1d.value || earliestNote.value
  }
}

// 上一次历史记录的展示数据（根据选择的时间范围）
const lastNoteDisplayData = computed(() => {
  const selectedHistory = getSelectedHistoryData()
  if (!selectedHistory) {
    return null
  }

  const walletValue = getNumericValue(selectedHistory.walletValue)
  const orderValue = getNumericValue(selectedHistory.orderValue)
  const totalValue = walletValue + orderValue + selectedHistory.runningProcessValue + selectedHistory.markedAssetValue + selectedHistory.unmarkedAssetValue
  return {
    totalValue: totalValue,
    walletValue: walletValue,
    orderValue: orderValue,
    runningProcessValue: selectedHistory.runningProcessValue,
    markedAssetValue: selectedHistory.markedAssetValue,
    unmarkedAssetValue: selectedHistory.unmarkedAssetValue
  }
})

// 变化数据计算
interface ChangeData {
  diff: number
  percent: number | null
  hasChange: boolean
}

const calculateChange = (current: number, last: number | null): ChangeData => {
  if (last === null || last === undefined) {
    return { diff: 0, percent: null, hasChange: false }
  }
  const diff = current - last
  const percent = last !== 0 ? (diff / last) * 100 : (diff > 0 ? Infinity : diff < 0 ? -Infinity : 0)
  return { diff, percent, hasChange: true }
}

// 各项指标的变化
const changeData = computed(() => {
  const current = displayData.value
  const last = lastNoteDisplayData.value

  if (!last) {
    return {
      totalValue: { diff: 0, percent: null, hasChange: false },
      walletValue: { diff: 0, percent: null, hasChange: false },
      orderValue: { diff: 0, percent: null, hasChange: false },
      runningProcessValue: { diff: 0, percent: null, hasChange: false },
      markedAssetValue: { diff: 0, percent: null, hasChange: false },
      unmarkedAssetValue: { diff: 0, percent: null, hasChange: false }
    }
  }

  // 计算总价值变化（考虑开关状态）
  const currentTotal = includeMarkedAssets.value ? current.totalValue : (current.totalValue - current.unmarkedAssetValue)
  const lastTotal = includeMarkedAssets.value ? last.totalValue : (last.totalValue - last.unmarkedAssetValue)

  return {
    totalValue: calculateChange(currentTotal, lastTotal),
    walletValue: calculateChange(current.walletValue, last.walletValue),
    orderValue: calculateChange(current.orderValue, last.orderValue),
    runningProcessValue: calculateChange(current.runningProcessValue, last.runningProcessValue),
    markedAssetValue: calculateChange(current.markedAssetValue, last.markedAssetValue),
    unmarkedAssetValue: calculateChange(current.unmarkedAssetValue, last.unmarkedAssetValue)
  }
})


// 计算显示的总价值（根据开关状态）
const displayTotalValue = computed(() => {
  if (!displayData.value) return 0
  if (includeMarkedAssets.value) {
    return displayData.value.totalValue
  } else {
    return displayData.value.totalValue - displayData.value.unmarkedAssetValue
  }
})

// 饼状图数据
const pieChartData = computed(() => {
  if (!displayData.value) return []

  const data = []

  data.push({
    name: '钱包总价值',
    value: displayData.value.walletValue
  })
  data.push({
    name: '订单总价值',
    value: displayData.value.orderValue
  })
  data.push({
    name: '运行中流程价值',
    value: displayData.value.runningProcessValue
  })
  data.push({
    name: '标记资产价值',
    value: displayData.value.markedAssetValue
  })

  if (includeMarkedAssets.value) {
    data.push({
      name: '非标记资产价值',
      value: displayData.value.unmarkedAssetValue
    })
  }

  return data
})

// 初始化饼状图
const initPieChart = () => {
  const c = getChartThemeColors()
  if (!pieChartRef.value) return

  const data = pieChartData.value
  if (!data || data.length === 0) {
    if (pieChartInstance) {
      pieChartInstance.dispose()
      pieChartInstance = null
    }
    return
  }

  if (!pieChartInstance) {
    pieChartInstance = echarts.init(pieChartRef.value)
  }

  const total = data.reduce((sum, item) => sum + item.value, 0)

  const option: EChartsOption = {
    title: {
      text: '资产价值分布',
      left: 'center',
      textStyle: {
        fontSize: 16,
        color: c.text
      }
    },
    tooltip: {
      ...themedTooltip(c),
      trigger: 'item',
      formatter: (params: unknown) => {
        const p = params as { name: string; value: number }
        const percentage = total > 0 ? ((p.value / total) * 100).toFixed(2) : '0'
        return `${p.name}<br/>价值: ${formatNumber(p.value)} ISK<br/>占比: ${percentage}%`
      }
    },
    legend: {
      orient: 'vertical',
      left: 'left',
      top: 'middle',
      textStyle: {
        color: c.textSecondary
      }
    },
    series: [
      {
        name: '资产价值',
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: c.surface,
          borderWidth: 2
        },
        label: {
          show: true,
          color: c.text,
          formatter: (params: unknown) => {
            const p = params as { name: string; value: number }
            const percentage = total > 0 ? ((p.value / total) * 100).toFixed(1) : '0'
            return `${p.name}\n${percentage}%`
          }
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 16,
            fontWeight: 'bold',
            color: c.text
          }
        },
        data: data
      }
    ]
  }

  pieChartInstance.setOption(option, true)
  pieChartInstance.resize()
}

// 更新图表
const updateChart = async () => {
  await nextTick()
  if (pieChartRef.value) {
    initPieChart()
  }
}

// 获取角色列表
const fetchCharacterList = async () => {
  try {
    const response = await http.get('/user/list')
    const data = await handleApiResponse<ApiResponse<Array<{ name: string; characterId: number | string }>>>(response)

    if (data && data.data) {
      // 使用 Map 去重，确保每个 characterId 只出现一次
      const uniqueChars = new Map<number, { name: string; characterId: number }>()

      data.data.forEach(char => {
        // 确保 characterId 是数字类型
        const characterId = typeof char.characterId === 'string'
          ? parseInt(char.characterId, 10)
          : Number(char.characterId)

        // 跳过无效的 ID
        if (isNaN(characterId) || characterId <= 0) {
          return
        }

        // 如果已存在，保留第一个
        if (!uniqueChars.has(characterId)) {
          uniqueChars.set(characterId, {
            name: char.name,
            characterId: characterId
          })
        }
      })

      // 转换为选项数组，确保 value 是数字类型
      characterOptions.value = Array.from(uniqueChars.values()).map(char => ({
        value: Number(char.characterId),
        label: char.name
      }))

      // 构建角色ID到名称的映射
      characterIdToNameMap.value = {}
      uniqueChars.forEach((char, id) => {
        characterIdToNameMap.value[Number(id)] = char.name
      })

      // 如果角色列表加载完成且尚未从本地存储恢复，尝试恢复设置
      if (!hasRestoredFromStorage.value) {
        const savedIds = loadFilterFromStorage()
        if (savedIds.length > 0) {
          // 验证保存的 ID 是否仍然有效
          const validIds = new Set(characterOptions.value.map(opt => opt.value))
          const validSavedIds = savedIds.filter(id => validIds.has(id))
          if (validSavedIds.length > 0) {
            selectedCharacterIdsRaw.value = validSavedIds
          }
        }
        hasRestoredFromStorage.value = true
      }
    }
  } catch (error) {
    console.error('获取角色列表失败:', error)
    ElMessage.error('获取角色列表失败')
  }
}

// 立刻刷新
const handleRefresh = async (forceRefresh: boolean = false) => {
  loading.value = true
  try {
    // 构建请求体
    const requestBody: { character_ids?: number[]; asset_mission_keys?: string[]; force_refresh?: boolean } = {
      force_refresh: forceRefresh
    }
    if (selectedCharacterIds.value.length > 0) {
      requestBody.character_ids = selectedCharacterIds.value
    }
    if (selectedAssetMissionKeys.value.length > 0) {
      requestBody.asset_mission_keys = selectedAssetMissionKeys.value
    }

    // 调用后端接口获取数据
    const response = await http.post('/EVE/home/overview', requestBody)
    const data = await handleApiResponse<ApiResponse<OverviewResponse>>(response)

    // 如果 API 返回成功，使用 API 数据；否则设置为 null 显示空状态
    if (data) {
      overviewData.value = data.data.today
      // 保存多个时间点的历史数据
      lastNoteData.value = data.data.last_note  // 保持向后兼容
      lastNote1d.value = data.data.last_note_1d
      lastNote7d.value = data.data.last_note_7d
      lastNote30d.value = data.data.last_note_30d
      earliestNote.value = data.data.earliest_note
      await updateChart()
      ElMessage.success('刷新成功')
    } else {
      // API 返回 null，设置为空数据状态
      overviewData.value = null
      lastNoteData.value = null
      lastNote1d.value = null
      lastNote7d.value = null
      lastNote30d.value = null
      earliestNote.value = null
      await updateChart()
    }
  } catch (error) {
    console.error('刷新失败:', error)
    ElMessage.error('刷新失败')
    // 发生错误时设置为空数据状态
    overviewData.value = null
    await updateChart()
  } finally {
    loading.value = false
  }
  console.log('overviewData.value', overviewData.value)
}

// 钱包筛选
const handleWalletFilter = async () => {
  // 如果角色列表未加载，先加载
  if (characterOptions.value.length === 0) {
    await fetchCharacterList()
  }

  filterDialogVisible.value = true
}

// 确认筛选
const confirmFilter = () => {
  filterDialogVisible.value = false
  // 筛选后自动刷新数据
  handleRefresh(true)
}

// 取消筛选
const cancelFilter = () => {
  filterDialogVisible.value = false
}

// 清空筛选
const clearFilter = () => {
  selectedCharacterIdsRaw.value = []
  localStorage.removeItem(STORAGE_KEY)
  filterDialogVisible.value = false
  // 清空筛选后自动刷新数据
  handleRefresh(true)
}

// 获取资产拉取任务列表
const fetchAssetMissionList = async () => {
  try {
    const response = await http.get('/EVE/asset/getAssetPullMissions')
    const data = await handleApiResponse<ApiResponse<Array<{ subject_type: string; subject_name: string; subject_id: number; is_abnormal?: boolean }>>>(response)

    if (data && data.data) {
      // 排除异常任务，只将正常任务加入资产筛选选项
      const validMissions = data.data.filter(mission => !mission.is_abnormal)
      // 转换为选项数组，value 格式为 "{subject_type}_{subject_id}"
      assetMissionOptions.value = validMissions.map(mission => ({
        value: `${mission.subject_type}_${mission.subject_id}`,
        label: mission.subject_name
      }))

      // 如果资产任务列表加载完成且尚未从本地存储恢复，尝试恢复设置
      if (!hasRestoredAssetFilterFromStorage.value) {
        const savedKeys = loadAssetFilterFromStorage()
        if (savedKeys.length > 0) {
          // 验证保存的 keys 是否仍然有效
          const validKeys = new Set(assetMissionOptions.value.map(opt => opt.value))
          const validSavedKeys = savedKeys.filter(key => validKeys.has(key))
          if (validSavedKeys.length > 0) {
            selectedAssetMissionKeysRaw.value = validSavedKeys
          }
        }
        hasRestoredAssetFilterFromStorage.value = true
      }
    }
  } catch (error) {
    console.error('获取资产拉取任务列表失败:', error)
    ElMessage.error('获取资产拉取任务列表失败')
  }
}

// 资产筛选
const handleAssetFilter = async () => {
  // 如果资产任务列表未加载，先加载
  if (assetMissionOptions.value.length === 0) {
    await fetchAssetMissionList()
  }

  assetFilterDialogVisible.value = true
}

// 确认资产筛选
const confirmAssetFilter = () => {
  assetFilterDialogVisible.value = false
  // 筛选后自动刷新数据
  handleRefresh(true)
}

// 取消资产筛选
const cancelAssetFilter = () => {
  assetFilterDialogVisible.value = false
}

// 清空资产筛选
const clearAssetFilter = () => {
  selectedAssetMissionKeysRaw.value = []
  localStorage.removeItem(ASSET_STORAGE_KEY)
  assetFilterDialogVisible.value = false
  // 清空筛选后自动刷新数据
  handleRefresh(true)
}

// 物品搜索相关函数
interface TypeItem {
  value: string
}

const fetchTypeSuggestions = async (queryString: string, cb: (suggestions: TypeItem[]) => void) => {
  try {
    const res = await http.post('/EVE/industry/getTypeSuggestionsList', {
      type_name: queryString
    })
    const data = await res.json()
    const results = queryString ? (data.data || []) : []
    cb(results)
  } catch (error) {
    console.error('获取物品建议失败:', error)
    cb([])
  }
}

// 打开资产搜索弹窗
const handleAssetSearch = () => {
  assetSearchDialogVisible.value = true
}

// 执行资产搜索
const handleSearchAsset = async () => {
  if (!assetSearchForm.value.item_name) {
    ElMessage.warning('请输入物品名称')
    return
  }

  assetSearchLoading.value = true
  try {
    const payload: { item_name: string } = {
      item_name: assetSearchForm.value.item_name
    }

    const res = await http.post('/EVE/asset/searchContainerByItemNameAndQuantity', payload)
    const data = await res.json()

    if (data.status !== 200) {
      ElMessage.error(data.message || '搜索失败')
      return
    }

    assetSearchForm.value.data = data.data || []
    if (assetSearchForm.value.data.length === 0) {
      ElMessage.info('未找到符合条件的物品')
    }
  } catch (error) {
    console.error('搜索失败:', error)
    ElMessage.error('搜索失败')
  } finally {
    assetSearchLoading.value = false
  }
}

// 监听开关变化
const handleSwitchChange = () => {
  saveIncludeUnmarkedToStorage(includeMarkedAssets.value)
  updateChart()
}

// 处理钱包卡片点击事件
const handleWalletCardClick = () => {
  if (!overviewData.value) {
    ElMessage.warning('暂无数据')
    return
  }

  const walletValue = overviewData.value.walletValue

  // 如果是对象类型，转换为列表格式
  if (typeof walletValue === 'object' && walletValue !== null) {
    const details: CharacterWalletDetail[] = Object.entries(walletValue)
      .map(([characterName, value]) => ({
        characterName,
        walletValue: typeof value === 'number' ? value : 0
      }))
      .sort((a, b) => b.walletValue - a.walletValue) // 按钱包价值降序排序

    walletDetailList.value = details
    walletDetailTotal.value = details.reduce((sum, item) => sum + item.walletValue, 0)
  } else {
    // 如果是数字类型，显示提示信息
    walletDetailList.value = []
    walletDetailTotal.value = typeof walletValue === 'number' ? walletValue : 0
  }

  walletDetailDialogVisible.value = true
}

// 处理订单卡片点击事件
const handleOrderCardClick = async () => {
  if (!overviewData.value) {
    ElMessage.warning('暂无数据')
    return
  }

  orderDetailLoading.value = true
  orderDetailDialogVisible.value = true

  try {
    // 构建请求体，支持角色筛选
    const requestBody: { character_ids?: number[] } = {}
    if (selectedCharacterIds.value.length > 0) {
      requestBody.character_ids = selectedCharacterIds.value
    }

    // 调用后端接口获取订单详情
    const response = await http.post('/EVE/home/orderDetails', requestBody)
    const data = await handleApiResponse<ApiResponse<OrderDetail[]>>(response)

    if (data && data.data) {
      orderDetailList.value = data.data
      // 计算总价值
      orderDetailTotal.value = data.data.reduce((sum, item) => sum + item.remaining_value, 0)

      if (orderDetailList.value.length === 0) {
        ElMessage.info('暂无订单数据')
      }
    } else {
      orderDetailList.value = []
      orderDetailTotal.value = 0
      ElMessage.warning('获取订单详情失败')
    }
  } catch (error) {
    console.error('获取订单详情失败:', error)
    ElMessage.error('获取订单详情失败')
    orderDetailList.value = []
    orderDetailTotal.value = 0
  } finally {
    orderDetailLoading.value = false
  }
}

// 处理运行中流程价值卡片点击事件
const handleRunningProcessCardClick = async () => {
  if (!overviewData.value) {
    ElMessage.warning('暂无数据')
    return
  }

  runningJobsLoading.value = true
  runningJobsDialogVisible.value = true

  try {
    // 调用后端接口获取运行中任务详情
    const response = await http.post('/EVE/home/runningJobsDetails', {})
    const data = await handleApiResponse<ApiResponse<{ detail_list: RunningJobDetail[]; summary_list: RunningJobSummary[]; character_summary_list: CharacterSummary[] }>>(response)

    if (data && data.data) {
      runningJobsDetailList.value = data.data.detail_list || []
      runningJobsSummaryList.value = data.data.summary_list || []
      runningJobsCharacterSummaryList.value = data.data.character_summary_list || []

      if (runningJobsDetailList.value.length === 0 && runningJobsSummaryList.value.length === 0 && runningJobsCharacterSummaryList.value.length === 0) {
        ElMessage.info('暂无运行中任务数据')
      }
    } else {
      runningJobsDetailList.value = []
      runningJobsSummaryList.value = []
      runningJobsCharacterSummaryList.value = []
      ElMessage.warning('获取运行中任务详情失败')
    }
  } catch (error) {
    console.error('获取运行中任务详情失败:', error)
    ElMessage.error('获取运行中任务详情失败')
    runningJobsDetailList.value = []
    runningJobsSummaryList.value = []
    runningJobsCharacterSummaryList.value = []
  } finally {
    runningJobsLoading.value = false
  }
}

// 切换运行中任务视图模式
const switchRunningJobsView = (mode: 'detail' | 'summary' | 'character') => {
  runningJobsViewMode.value = mode
}

// 监听窗口大小变化
const handleResize = () => {
  if (pieChartInstance) {
    pieChartInstance.resize()
  }
}

onMounted(async () => {
  cleanupThemeWatcher = onThemeTokenChange(() => {
    updateChart()
  })
  await nextTick()
  // 从本地存储加载"考虑非标记资产"设置
  includeMarkedAssets.value = loadIncludeUnmarkedFromStorage()
  // 从本地存储加载时间范围选择
  selectedTimeRange.value = loadTimeRangeFromStorage()
  initPieChart()
  window.addEventListener('resize', handleResize)
  // 初始化时加载角色列表和资产拉取任务列表
  await Promise.all([fetchCharacterList(), fetchAssetMissionList()])
  handleRefresh()
})

onUnmounted(() => {
  cleanupThemeWatcher?.()
  cleanupThemeWatcher = null
  if (pieChartInstance) {
    pieChartInstance.dispose()
    pieChartInstance = null
  }
  window.removeEventListener('resize', handleResize)
})

// 所有数据项的过渡动画配置
const transitionConfig = {
  duration: 2000,
  transition: (t: number) => t * (2 - t), // 使用 ease-out 缓动函数，使动画更自然
}

// 总价值的过渡动画
const totalValueSource = computed(() => displayTotalValue.value ?? 0)
const outputTotalValue = useTransition(totalValueSource, transitionConfig)

// 钱包总价值的过渡动画
const walletValueSource = computed(() => displayData.value?.walletValue ?? 0)
const outputWalletToDisplayValue = useTransition(walletValueSource, transitionConfig)

// 订单总价值的过渡动画
const orderValueSource = computed(() => displayData.value?.orderValue ?? 0)
const outputOrderValue = useTransition(orderValueSource, transitionConfig)

// 运行中流程价值的过渡动画
const runningProcessValueSource = computed(() => displayData.value?.runningProcessValue ?? 0)
const outputRunningProcessValue = useTransition(runningProcessValueSource, transitionConfig)

// 标记资产价值的过渡动画
const markedAssetValueSource = computed(() => displayData.value?.markedAssetValue ?? 0)
const outputMarkedAssetValue = useTransition(markedAssetValueSource, transitionConfig)

// 非标记资产价值的过渡动画
const unmarkedAssetValueSource = computed(() => displayData.value?.unmarkedAssetValue ?? 0)
const outputUnmarkedAssetValue = useTransition(unmarkedAssetValueSource, transitionConfig)

</script>

<template>
  <div class="overview-container" v-loading="loading" element-loading-text="正在刷新数据，请稍候..."
    element-loading-background="rgba(255, 255, 255, 0.95)">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-button type="primary" :icon="Refresh" :loading="loading" @click="handleRefresh(true)">
        立刻刷新
      </el-button>
      <el-button :icon="Filter" @click="handleWalletFilter">
        钱包筛选
        <span v-if="selectedCharacterIds.length > 0" class="filter-badge">
          ({{ selectedCharacterIds.length }})
        </span>
      </el-button>
      <el-button :icon="Filter" @click="handleAssetFilter">
        资产筛选
        <span v-if="selectedAssetMissionKeys.length > 0" class="filter-badge">
          ({{ selectedAssetMissionKeys.length }})
        </span>
      </el-button>
      <el-button type="primary" :icon="Refresh" @click="handleAssetSearch">
        资产查找
      </el-button>
      <div class="time-range-container">
        <span class="time-range-label">时间范围：</span>
        <el-radio-group v-model="selectedTimeRange" @change="saveTimeRangeToStorage(selectedTimeRange)">
          <el-radio-button label="1d">一天</el-radio-button>
          <el-radio-button label="7d">本周</el-radio-button>
          <el-radio-button label="30d">本月</el-radio-button>
        </el-radio-group>
      </div>
      <div class="switch-container">
        <span class="switch-label">考虑非标记资产</span>
        <el-switch v-model="includeMarkedAssets" @change="handleSwitchChange" />
      </div>
    </div>

    <!-- 数据展示 -->
    <div v-if="!isEmpty" class="data-section">
      <el-row :gutter="24">
        <!-- 总价值 -->
        <el-col>
          <el-card shadow="hover" class="data-card data-card-total">
            <div class="data-card-content">
              <div class="data-header">
                <el-icon class="data-icon data-icon-total">
                  <Money />
                </el-icon>
                <div class="data-label">总价值</div>
              </div>
              <div class="data-value data-value-total">{{ formatNumber(outputTotalValue) }} ISK</div>
              <div v-if="changeData.totalValue.hasChange"
                :class="['data-change', getChangeColorClass(changeData.totalValue)]">
                {{ formatChange(changeData.totalValue) }}
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
      <el-row :gutter="24">
        <!-- 钱包总价值 -->
        <el-col :xs="24" :sm="12" :md="8" :lg="6">
          <el-card shadow="hover" class="data-card data-card-wallet" @click="handleWalletCardClick">
            <div class="data-card-content">
              <div class="data-header">
                <el-icon class="data-icon data-icon-wallet">
                  <Wallet />
                </el-icon>
                <div class="data-label">钱包总价值</div>
              </div>
              <div class="data-value">{{ formatNumber(outputWalletToDisplayValue) }} ISK</div>
              <div v-if="changeData.walletValue.hasChange"
                :class="['data-change', getChangeColorClass(changeData.walletValue)]">
                {{ formatChange(changeData.walletValue) }}
              </div>
            </div>
          </el-card>
        </el-col>

        <!-- 订单总价值 -->
        <el-col :xs="24" :sm="12" :md="8" :lg="6">
          <el-card shadow="hover" class="data-card data-card-order" @click="handleOrderCardClick">
            <div class="data-card-content">
              <div class="data-header">
                <el-icon class="data-icon data-icon-order">
                  <ShoppingCart />
                </el-icon>
                <div class="data-label">订单总价值</div>
              </div>
              <div class="data-value">{{ formatNumber(outputOrderValue) }} ISK</div>
              <div v-if="changeData.orderValue.hasChange"
                :class="['data-change', getChangeColorClass(changeData.orderValue)]">
                {{ formatChange(changeData.orderValue) }}
              </div>
            </div>
          </el-card>
        </el-col>

        <!-- 运行中流程价值 -->
        <el-col :xs="24" :sm="12" :md="8" :lg="6">
          <el-card shadow="hover" class="data-card data-card-process" @click="handleRunningProcessCardClick">
            <div class="data-card-content">
              <div class="data-header">
                <el-icon class="data-icon data-icon-process">
                  <Timer />
                </el-icon>
                <div class="data-label">运行中流程价值</div>
              </div>
              <div class="data-value">{{ formatNumber(outputRunningProcessValue) }} ISK</div>
              <div v-if="changeData.runningProcessValue.hasChange"
                :class="['data-change', getChangeColorClass(changeData.runningProcessValue)]">
                {{ formatChange(changeData.runningProcessValue) }}
              </div>
            </div>
          </el-card>
        </el-col>

        <!-- 标记资产价值 -->
        <el-col :xs="24" :sm="12" :md="8" :lg="6">
          <el-card shadow="hover" class="data-card data-card-marked">
            <div class="data-card-content">
              <div class="data-header">
                <el-icon class="data-icon data-icon-marked">
                  <Star />
                </el-icon>
                <div class="data-label">标记资产价值</div>
              </div>
              <div class="data-value">{{ formatNumber(outputMarkedAssetValue) }} ISK</div>
              <div v-if="changeData.markedAssetValue.hasChange"
                :class="['data-change', getChangeColorClass(changeData.markedAssetValue)]">
                {{ formatChange(changeData.markedAssetValue) }}
              </div>
            </div>
          </el-card>
        </el-col>

        <!-- 非标记资产价值（根据开关显示） -->
        <el-col v-if="includeMarkedAssets" :xs="24" :sm="12" :md="8" :lg="6">
          <el-card shadow="hover" class="data-card data-card-unmarked">
            <div class="data-card-content">
              <div class="data-header">
                <el-icon class="data-icon data-icon-unmarked">
                  <Box />
                </el-icon>
                <div class="data-label">非标记资产价值</div>
              </div>
              <div class="data-value">{{ formatNumber(outputUnmarkedAssetValue) }} ISK</div>
              <div v-if="changeData.unmarkedAssetValue.hasChange"
                :class="['data-change', getChangeColorClass(changeData.unmarkedAssetValue)]">
                {{ formatChange(changeData.unmarkedAssetValue) }}
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 空数据状态 -->
    <div v-else class="empty-section">
      <el-empty description="暂无数据，请点击刷新按钮获取数据" :image-size="200">
        <el-button type="primary" :icon="Refresh" :loading="loading" @click="handleRefresh">
          刷新数据
        </el-button>
      </el-empty>
    </div>

    <!-- 饼状图 -->
    <div class="chart-section">
      <el-card shadow="hover">
        <div v-if="!isEmpty" ref="pieChartRef" class="pie-chart"></div>
        <el-empty v-else description="暂无数据" :image-size="120" />
      </el-card>
    </div>

    <!-- 钱包筛选弹窗 -->
    <el-dialog v-model="filterDialogVisible" title="钱包筛选" width="500px" :close-on-click-modal="false">
      <div class="filter-dialog-content">
        <div class="filter-label">选择角色（可多选）：</div>
        <el-select v-model="selectedCharacterIds" multiple placeholder="请选择角色" style="width: 100%" clearable
          collapse-tags collapse-tags-tooltip filterable>
          <el-option v-for="option in characterOptions" :key="`char-${option.value}`" :label="option.label"
            :value="option.value" />
        </el-select>
        <div v-if="selectedCharacterIds.length > 0" class="filter-tip">
          已选择 {{ selectedCharacterIds.length }} 个角色
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="clearFilter">清空筛选</el-button>
          <el-button @click="cancelFilter">取消</el-button>
          <el-button type="primary" @click="confirmFilter">确认</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 资产筛选弹窗 -->
    <el-dialog v-model="assetFilterDialogVisible" title="资产筛选" width="500px" :close-on-click-modal="false">
      <div class="filter-dialog-content">
        <div class="filter-label">选择资产拉取任务（可多选）：</div>
        <el-select v-model="selectedAssetMissionKeys" multiple placeholder="请选择资产拉取任务" style="width: 100%" clearable
          collapse-tags collapse-tags-tooltip filterable>
          <el-option v-for="option in assetMissionOptions" :key="`asset-${option.value}`" :label="option.label"
            :value="option.value" />
        </el-select>
        <div v-if="selectedAssetMissionKeys.length > 0" class="filter-tip">
          已选择 {{ selectedAssetMissionKeys.length }} 个任务
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="clearAssetFilter">清空筛选</el-button>
          <el-button @click="cancelAssetFilter">取消</el-button>
          <el-button type="primary" @click="confirmAssetFilter">确认</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 物品搜索弹窗 -->
    <el-dialog v-model="assetSearchDialogVisible" title="物品搜索" width="70%" :close-on-click-modal="false">
      <el-form :model="assetSearchForm" label-width="120px">
        <el-form-item label="物品名">
          <el-autocomplete v-model="assetSearchForm.item_name" :fetch-suggestions="fetchTypeSuggestions"
            value-key="value" placeholder="请输入物品名称" style="width: 100%" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearchAsset" :loading="assetSearchLoading">
            搜索
          </el-button>
        </el-form-item>
        <el-form-item label="搜索结果">
          <el-table :data="assetSearchForm.data" border v-loading="assetSearchLoading" max-height="700px"
            show-overflow-tooltip>
            <el-table-column label="名称" prop="asset.type_name" />
            <el-table-column label="数量" prop="asset.quantity" />
            <el-table-column label="建筑" prop="structure.structure_name" />
            <el-table-column label="容器ID" prop="container.item_id" />
            <el-table-column label="容器位置" prop="asset.location_flag" />
          </el-table>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="assetSearchDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 钱包详情弹窗 -->
    <el-dialog v-model="walletDetailDialogVisible" title="钱包详情" width="600px" :close-on-click-modal="false">
      <div class="wallet-detail-content">
        <div v-if="walletDetailList.length > 0">
          <el-table :data="walletDetailList" border max-height="500px" show-overflow-tooltip>
            <el-table-column label="角色名称" prop="characterName" width="200">
              <template #default="{ row }">
                <span style="font-weight: 500;">{{ row.characterName }}</span>
              </template>
            </el-table-column>
            <el-table-column label="钱包价值" prop="walletValue" align="right">
              <template #default="{ row }">
                <span style="color: #67c23a; font-weight: 600;">{{ formatNumber(row.walletValue) }} ISK</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="wallet-detail-total">
            <span class="total-label">总计：</span>
            <span class="total-value">{{ formatNumber(walletDetailTotal) }} ISK</span>
          </div>
        </div>
        <div v-else class="wallet-detail-empty">
          <el-empty description="暂无详细数据" :image-size="100" />
          <div v-if="walletDetailTotal > 0" class="wallet-detail-total">
            <span class="total-label">总价值：</span>
            <span class="total-value">{{ formatNumber(walletDetailTotal) }} ISK</span>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="walletDetailDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 订单详情弹窗 -->
    <el-dialog v-model="orderDetailDialogVisible" title="订单详情" width="90%" :close-on-click-modal="false">
      <div class="order-detail-content" v-loading="orderDetailLoading" element-loading-text="正在加载订单数据...">
        <div v-if="orderDetailList.length > 0">
          <el-table :data="orderDetailList" border max-height="600px" show-overflow-tooltip stripe>
            <el-table-column label="角色名称" prop="character_name" width="120" fixed="left">
              <template #default="{ row }">
                <span style="font-weight: 500;">{{ row.character_name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="物品名称" prop="type_name" width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <span>{{ row.type_name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="订单种类" prop="order_type" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_buy_order ? 'success' : 'warning'" size="small">
                  {{ row.order_type }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="订单地点" prop="location_name" width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <span>{{ row.location_name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="总数量" prop="volume_total" width="100" align="right">
              <template #default="{ row }">
                <span>{{ row.volume_total.toLocaleString('zh-CN') }}</span>
              </template>
            </el-table-column>
            <el-table-column label="剩余数量" prop="volume_remain" width="100" align="right">
              <template #default="{ row }">
                <span>{{ row.volume_remain.toLocaleString('zh-CN') }}</span>
              </template>
            </el-table-column>
            <el-table-column label="完成百分比" prop="completion_percent" width="150" align="center">
              <template #default="{ row }">
                <el-progress :percentage="row.completion_percent" :color="getProgressColor(row.completion_percent)" />
              </template>
            </el-table-column>
            <el-table-column label="单价" prop="price" width="120" align="right">
              <template #default="{ row }">
                <span>{{ formatNumber(row.price) }} ISK</span>
              </template>
            </el-table-column>
            <el-table-column label="剩余订单价值" prop="remaining_value" width="150" align="right">
              <template #default="{ row }">
                <span style="color: #e6a23c; font-weight: 600;">{{ formatNumber(row.remaining_value) }} ISK</span>
              </template>
            </el-table-column>
            <el-table-column label="剩余时间" prop="remaining_time_minutes" width="180">
              <template #default="{ row }">
                <span :style="getRemainingTimeStyle(row.remaining_time_minutes)">
                  {{ formatRemainingTime(row.remaining_time_minutes) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <div class="order-detail-total">
            <span class="total-label">剩余订单总价值：</span>
            <span class="total-value">{{ formatNumber(orderDetailTotal) }} ISK</span>
          </div>
        </div>
        <div v-else class="order-detail-empty">
          <el-empty description="暂无订单数据" :image-size="100" />
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="orderDetailDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 运行中任务详情弹窗 -->
    <el-dialog v-model="runningJobsDialogVisible" title="运行中任务详情" width="90%" :close-on-click-modal="false">
      <div class="running-jobs-detail-content" v-loading="runningJobsLoading" element-loading-text="正在加载任务数据...">
        <!-- 视图切换按钮 -->
        <div class="view-switch-container">
          <el-button-group>
            <el-button :type="runningJobsViewMode === 'detail' ? 'primary' : 'default'"
              @click="switchRunningJobsView('detail')">
              详细信息
            </el-button>
            <el-button :type="runningJobsViewMode === 'summary' ? 'primary' : 'default'"
              @click="switchRunningJobsView('summary')">
              分类汇总
            </el-button>
            <el-button :type="runningJobsViewMode === 'character' ? 'primary' : 'default'"
              @click="switchRunningJobsView('character')">
              角色占用情况
            </el-button>
          </el-button-group>
        </div>

        <!-- 详细信息视图 -->
        <div v-if="runningJobsViewMode === 'detail'">
          <div v-if="runningJobsDetailList.length > 0">
            <el-table :data="runningJobsDetailList" border max-height="600px" show-overflow-tooltip stripe>
              <el-table-column label="任务类型" prop="job_type" width="100" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.job_type === '个人' ? 'success' : 'info'" size="small">
                    {{ row.job_type }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="活动类型" prop="activity_type" width="100" align="center">
                <template #default="{ row }">
                  <span
                    :style="row.activity_type === '制造' ? 'color: #409eff; font-weight: 700; font-size: 15px;' : 'color: #e6a23c; font-weight: 700; font-size: 15px;'">
                    {{ row.activity_type }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="物品图标" width="80" align="center">
                <template #default="{ row }">
                  <img :src="`https://imageserver.eveonline.com/types/${row.product_type_id}/icon`" alt="物品图标"
                    width="40" height="40" style="border-radius: 4px;"
                    @error="(e: any) => { e.target.style.display = 'none' }" />
                </template>
              </el-table-column>
              <el-table-column label="物品名称" prop="product_name_zh" width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <div>
                    <div style="font-weight: 500;">{{ row.product_name_zh }}</div>
                    <div style="font-size: 12px; color: #909399;">{{ row.product_name }}</div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="产量" width="150" align="center">
                <template #default="{ row }">
                  <span>{{ row.runs.toLocaleString('zh-CN') }} × {{ row.product_quantity_per_run.toLocaleString('zh-CN')
                    }} = {{ row.total_quantity.toLocaleString('zh-CN') }}</span>
                </template>
              </el-table-column>
              <el-table-column label="任务进度" prop="progress_percent" width="150" align="center" sortable>
                <template #default="{ row }">
                  <el-progress :percentage="row.progress_percent" :color="getProgressColor(row.progress_percent)" />
                </template>
              </el-table-column>
              <el-table-column label="消耗" prop="cost" width="120" align="right">
                <template #default="{ row }">
                  <span>{{ formatNumber(row.cost) }} ISK</span>
                </template>
              </el-table-column>
              <el-table-column label="启动角色" prop="installer_name" width="150" show-overflow-tooltip>
                <template #default="{ row }">
                  <span style="font-weight: 500;">{{ row.installer_name }}</span>
                </template>
              </el-table-column>
              <el-table-column label="生产价值" prop="value" width="150" align="right" sortable>
                <template #default="{ row }">
                  <span style="color: #67c23a; font-weight: 600;">{{ formatNumber(row.value) }} ISK</span>
                </template>
              </el-table-column>
            </el-table>
            <div class="running-jobs-detail-total">
              <span class="total-label">总生产价值：</span>
              <span class="total-value">{{formatNumber(runningJobsDetailList.reduce((sum, item) => sum + item.value,
                0))}}
                ISK</span>
            </div>
          </div>
          <div v-else class="running-jobs-detail-empty">
            <el-empty description="暂无运行中任务数据" :image-size="100" />
          </div>
        </div>

        <!-- 角色占用情况视图 -->
        <div v-if="runningJobsViewMode === 'character'">
          <div v-if="runningJobsCharacterSummaryList.length > 0">
            <el-table :data="runningJobsCharacterSummaryList" border max-height="600px" show-overflow-tooltip stripe>
              <el-table-column label="角色头像" width="100" align="center">
                <template #default="{ row }">
                  <img :src="`https://imageserver.eveonline.com/Character/${row.character_id}_64.jpg`" alt="角色头像"
                    width="64" height="64" style="border-radius: 8px; border: 2px solid #e4e7ed;"
                    @error="(e: any) => { e.target.style.display = 'none' }" />
                </template>
              </el-table-column>
              <el-table-column label="角色名" prop="character_name" width="200" show-overflow-tooltip fixed="left">
                <template #default="{ row }">
                  <span style="font-weight: 500;">{{ row.character_name }}</span>
                </template>
              </el-table-column>
              <el-table-column label="制造-运行中" prop="manufacturing_running_count" width="140" align="center" sortable>
                <template #default="{ row }">
                  <span style="color: #409eff; font-weight: 700; font-size: 18px;">{{ row.manufacturing_running_count
                  }}</span>
                </template>
              </el-table-column>
              <el-table-column label="制造-已完成" prop="manufacturing_completed_count" width="140" align="center" sortable>
                <template #default="{ row }">
                  <span style="color: #67c23a; font-weight: 700; font-size: 18px;">{{ row.manufacturing_completed_count
                  }}</span>
                </template>
              </el-table-column>
              <el-table-column label="反应-运行中" prop="reaction_running_count" width="140" align="center" sortable>
                <template #default="{ row }">
                  <span style="color: #e6a23c; font-weight: 700; font-size: 18px;">{{ row.reaction_running_count
                  }}</span>
                </template>
              </el-table-column>
              <el-table-column label="反应-已完成" prop="reaction_completed_count" width="140" align="center" sortable>
                <template #default="{ row }">
                  <span style="color: #67c23a; font-weight: 700; font-size: 18px;">{{ row.reaction_completed_count
                  }}</span>
                </template>
              </el-table-column>
              <el-table-column label="制造总数" width="120" align="center" sortable>
                <template #default="{ row }">
                  <span style="font-weight: 600; color: #409eff;">
                    {{ row.manufacturing_running_count + row.manufacturing_completed_count }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="反应总数" width="120" align="center" sortable>
                <template #default="{ row }">
                  <span style="font-weight: 600; color: #e6a23c;">
                    {{ row.reaction_running_count + row.reaction_completed_count }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="总任务数" width="120" align="center" sortable>
                <template #default="{ row }">
                  <span style="font-weight: 600; font-size: 16px;">
                    {{ row.manufacturing_running_count + row.manufacturing_completed_count + row.reaction_running_count
                      + row.reaction_completed_count }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
            <div class="running-jobs-character-total">
              <span class="total-label">总角色数：</span>
              <span class="total-value">{{ runningJobsCharacterSummaryList.length }}</span>
              <span class="total-label" style="margin-left: 20px;">制造任务总数：</span>
              <span class="total-value">{{runningJobsCharacterSummaryList.reduce((sum, item) => sum +
                item.manufacturing_running_count + item.manufacturing_completed_count, 0)}}</span>
              <span class="total-label" style="margin-left: 20px;">反应任务总数：</span>
              <span class="total-value">{{runningJobsCharacterSummaryList.reduce((sum, item) => sum +
                item.reaction_running_count + item.reaction_completed_count, 0)}}</span>
              <span class="total-label" style="margin-left: 20px;">总任务数：</span>
              <span class="total-value">{{runningJobsCharacterSummaryList.reduce((sum, item) => sum +
                item.manufacturing_running_count + item.manufacturing_completed_count + item.reaction_running_count +
                item.reaction_completed_count, 0)}}</span>
            </div>
          </div>
          <div v-else class="running-jobs-detail-empty">
            <el-empty description="暂无角色占用数据" :image-size="100" />
          </div>
        </div>

        <!-- 分类汇总视图 -->
        <div v-if="runningJobsViewMode === 'summary'">
          <div v-if="runningJobsSummaryList.length > 0">
            <el-row :gutter="20">
              <el-col v-for="item in runningJobsSummaryList" :key="item.product_type_id" :xs="24" :sm="12" :md="8"
                :lg="6" style="margin-bottom: 20px;">
                <el-card shadow="hover" class="summary-card" style="cursor: pointer;"
                  @click="switchRunningJobsView('detail')">
                  <div class="summary-card-content">
                    <div class="summary-icon-container">
                      <img :src="`https://imageserver.eveonline.com/types/${item.product_type_id}/icon`" alt="物品图标"
                        width="64" height="64" style="border-radius: 8px;"
                        @error="(e: any) => { e.target.style.display = 'none' }" />
                    </div>
                    <div class="summary-info">
                      <div class="summary-name" :title="item.product_name_zh">{{ item.product_name_zh }}</div>
                      <div class="summary-name-en" :title="item.product_name">{{ item.product_name }}</div>
                      <div class="summary-quantity">
                        <span class="summary-label">生产数量：</span>
                        <span class="summary-value">{{ item.total_quantity.toLocaleString('zh-CN') }}</span>
                      </div>
                      <div class="summary-value-text">
                        <span class="summary-label">生产价值：</span>
                        <span class="summary-value-number">{{ formatNumber(item.total_value) }} ISK</span>
                      </div>
                    </div>
                  </div>
                </el-card>
              </el-col>
            </el-row>
            <div class="running-jobs-summary-total">
              <span class="total-label">总生产价值：</span>
              <span class="total-value">{{formatNumber(runningJobsSummaryList.reduce((sum, item) => sum +
                item.total_value,
                0))}} ISK</span>
            </div>
          </div>
          <div v-else class="running-jobs-detail-empty">
            <el-empty description="暂无运行中任务数据" :image-size="100" />
          </div>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="runningJobsDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.overview-container {
  padding: 24px;
  position: relative;
  min-height: 400px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  padding: 20px 24px;
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  border: 1px solid rgba(0, 0, 0, 0.05);
}

.time-range-container {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.time-range-label {
  font-size: 15px;
  color: #606266;
  font-weight: 500;
  white-space: nowrap;
}

.switch-container {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 16px;
}

.switch-label {
  font-size: 15px;
  color: #606266;
  font-weight: 500;
}

.chart-section {
  margin-bottom: 24px;
}

.chart-section :deep(.el-card) {
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.pie-chart {
  width: 100%;
  height: 450px;
}

.data-section {
  margin-top: 24px;
}

.empty-section {
  margin-top: 40px;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

.data-card {
  margin-bottom: 24px;
  border-radius: 12px;
  transition: all 0.3s ease;
  overflow: hidden;
  border: 2px solid transparent;
}

.data-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.data-card :deep(.el-card__body) {
  padding: 28px 24px;
}

.data-card-content {
  text-align: center;
}

.data-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 16px;
}

.data-icon {
  font-size: 24px;
  width: 24px;
  height: 24px;
}

.data-icon-total {
  color: #409eff;
}

.data-icon-wallet {
  color: #67c23a;
}

.data-icon-order {
  color: #e6a23c;
}

.data-icon-process {
  color: #909399;
}

.data-icon-marked {
  color: #f56c6c;
}

.data-icon-unmarked {
  color: #909399;
}

.data-label {
  font-size: 16px;
  color: #606266;
  margin: 0;
  font-weight: 500;
}

.data-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  margin-bottom: 12px;
  line-height: 1.2;
}

.data-value-total {
  font-size: 36px;
  color: #303133;
}

.data-change {
  font-size: 14px;
  margin-top: 8px;
  font-weight: 500;
  padding: 4px 12px;
  border-radius: 6px;
  display: inline-block;
}

.data-change.change-positive {
  color: #67c23a;
  background-color: rgba(103, 194, 58, 0.1);
}

.data-change.change-negative {
  color: #f56c6c;
  background-color: rgba(245, 108, 108, 0.1);
}

.data-card-total {
  border-left: 4px solid #409eff;
  background: linear-gradient(135deg, #ffffff 0%, #ecf5ff 100%);
}

.data-card-total:hover {
  border-left-color: #409eff;
  box-shadow: 0 8px 24px rgba(64, 158, 255, 0.15);
}

.data-card-wallet {
  border-left: 4px solid #67c23a;
  background: linear-gradient(135deg, #ffffff 0%, #f0f9ff 100%);
  cursor: pointer;
  position: relative;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.data-card-wallet:hover {
  border-left-color: #67c23a;
  border-left-width: 6px;
  box-shadow: 0 12px 32px rgba(103, 194, 58, 0.25);
  transform: translateY(-6px) scale(1.02);
  background: linear-gradient(135deg, #ffffff 0%, #e8f5e9 100%);
}

.data-card-wallet:active {
  transform: translateY(-2px) scale(1.01);
  box-shadow: 0 8px 20px rgba(103, 194, 58, 0.2);
}

.data-card-order {
  border-left: 4px solid #e6a23c;
  background: linear-gradient(135deg, #ffffff 0%, #fff7ed 100%);
  cursor: pointer;
  position: relative;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.data-card-order:hover {
  border-left-color: #e6a23c;
  border-left-width: 6px;
  box-shadow: 0 12px 32px rgba(230, 162, 60, 0.25);
  transform: translateY(-6px) scale(1.02);
  background: linear-gradient(135deg, #ffffff 0%, #fff4e6 100%);
}

.data-card-order:active {
  transform: translateY(-2px) scale(1.01);
  box-shadow: 0 8px 20px rgba(230, 162, 60, 0.2);
}

.data-card-process {
  border-left: 4px solid #909399;
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
  cursor: pointer;
  position: relative;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.data-card-process:hover {
  border-left-color: #909399;
  border-left-width: 6px;
  box-shadow: 0 12px 32px rgba(144, 147, 153, 0.25);
  transform: translateY(-6px) scale(1.02);
  background: linear-gradient(135deg, #ffffff 0%, #f0f0f0 100%);
}

.data-card-process:active {
  transform: translateY(-2px) scale(1.01);
  box-shadow: 0 8px 20px rgba(144, 147, 153, 0.2);
}

.data-card-marked {
  border-left: 4px solid #f56c6c;
  background: linear-gradient(135deg, #ffffff 0%, #fef0f0 100%);
}

.data-card-marked:hover {
  border-left-color: #f56c6c;
  box-shadow: 0 8px 24px rgba(245, 108, 108, 0.15);
}

.data-card-unmarked {
  border-left: 4px solid #909399;
  background: linear-gradient(135deg, #ffffff 0%, #f5f7fa 100%);
}

.data-card-unmarked:hover {
  border-left-color: #909399;
  box-shadow: 0 8px 24px rgba(144, 147, 153, 0.15);
}

.filter-badge {
  margin-left: 4px;
  color: #409eff;
  font-weight: 500;
}

.filter-dialog-content {
  padding: 20px 0;
}

.filter-label {
  margin-bottom: 12px;
  font-size: 15px;
  color: #606266;
  font-weight: 500;
}

.filter-tip {
  margin-top: 12px;
  font-size: 13px;
  color: #909399;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

@media (max-width: 768px) {
  .overview-container {
    padding: 16px;
  }

  .toolbar {
    flex-direction: column;
    align-items: stretch;
    padding: 16px;
  }

  .time-range-container {
    margin-left: 0;
    justify-content: space-between;
    flex-wrap: wrap;
  }

  .switch-container {
    margin-left: 0;
    justify-content: space-between;
  }

  .data-value {
    font-size: 24px;
  }

  .data-value-total {
    font-size: 28px;
  }

  .data-label {
    font-size: 14px;
  }

  .data-icon {
    font-size: 20px;
    width: 20px;
    height: 20px;
  }

  .pie-chart {
    height: 350px;
  }
}

/* 加载遮罩样式优化 */
.overview-container :deep(.el-loading-mask) {
  border-radius: 12px;
  z-index: 2000;
}

.overview-container :deep(.el-loading-text) {
  font-size: 16px;
  font-weight: 500;
  color: #409eff;
  margin-top: 12px;
}

.overview-container :deep(.el-loading-spinner) {
  font-size: 32px;
}

.overview-container :deep(.el-loading-spinner .path) {
  stroke: #409eff;
}

/* 钱包详情弹窗样式 */
.wallet-detail-content {
  padding: 10px 0;
}

.wallet-detail-total {
  margin-top: 20px;
  padding: 16px;
  background: linear-gradient(135deg, #f0f9ff 0%, #e8f5e9 100%);
  border-radius: 8px;
  text-align: right;
  border: 1px solid rgba(103, 194, 58, 0.2);
}

.total-label {
  font-size: 16px;
  color: #606266;
  font-weight: 500;
  margin-right: 12px;
}

.total-value {
  font-size: 20px;
  color: #67c23a;
  font-weight: 700;
}

.wallet-detail-empty {
  padding: 40px 0;
  text-align: center;
}

/* 订单详情弹窗样式 */
.order-detail-content {
  padding: 10px 0;
}

.order-detail-total {
  margin-top: 20px;
  padding: 16px;
  background: linear-gradient(135deg, #fff7ed 0%, #fff4e6 100%);
  border-radius: 8px;
  text-align: right;
  border: 1px solid rgba(230, 162, 60, 0.2);
}

.order-detail-empty {
  padding: 40px 0;
  text-align: center;
}

/* 运行中任务详情弹窗样式 */
.running-jobs-detail-content {
  padding: 10px 0;
}

.view-switch-container {
  margin-bottom: 20px;
  display: flex;
  justify-content: flex-end;
}

.running-jobs-detail-total {
  margin-top: 20px;
  padding: 16px;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  border-radius: 8px;
  text-align: right;
  border: 1px solid rgba(144, 147, 153, 0.2);
}

.running-jobs-summary-total {
  margin-top: 20px;
  padding: 16px;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  border-radius: 8px;
  text-align: right;
  border: 1px solid rgba(144, 147, 153, 0.2);
}

.running-jobs-character-total {
  margin-top: 20px;
  padding: 16px;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  border-radius: 8px;
  text-align: right;
  border: 1px solid rgba(144, 147, 153, 0.2);
}

.running-jobs-detail-empty {
  padding: 40px 0;
  text-align: center;
}

/* 分类汇总卡片样式 */
.summary-card {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border: 2px solid transparent;
}

.summary-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  border-color: #909399;
}

.summary-card-content {
  text-align: center;
}

.summary-icon-container {
  margin-bottom: 12px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.summary-info {
  text-align: left;
}

.summary-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-name-en {
  font-size: 12px;
  color: #909399;
  margin-bottom: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-quantity {
  margin-bottom: 8px;
  font-size: 14px;
}

.summary-value-text {
  font-size: 14px;
}

.summary-label {
  color: #606266;
  margin-right: 8px;
}

.summary-value {
  color: #303133;
  font-weight: 500;
}

.summary-value-number {
  color: #67c23a;
  font-weight: 600;
  font-size: 16px;
}

/* Theme override */
.overview-container,
.toolbar,
.chart-section :deep(.el-card),
.data-card,
.summary-card,
.wallet-detail-total,
.order-detail-total,
.running-jobs-detail-total,
.running-jobs-summary-total,
.running-jobs-character-total {
  background: var(--k-color-surface) !important;
  border-color: var(--k-color-border) !important;
  color: var(--k-color-text) !important;
}

.toolbar {
  background: var(--k-color-surface-soft) !important;
}

.data-label,
.switch-label,
.time-range-label,
.summary-label,
.summary-name-en {
  color: var(--k-color-text-secondary) !important;
}

.data-value,
.data-value-total,
.summary-name {
  color: var(--k-color-text) !important;
}

.overview-container :deep(.el-loading-mask) {
  background-color: color-mix(in srgb, var(--k-color-surface) 92%, transparent) !important;
}
</style>
