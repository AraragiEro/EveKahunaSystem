<script setup lang="ts" name="HistoryView">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { ElMessage, ElMessageBox } from 'element-plus'
import { http } from '@/http'
import { handleApiResponse } from '@/utils/apiResponse'

// 数据接口
interface HistoryDataItem {
  date: string
  data: {
    walletValue: number
    orderValue: number
    runningProcessValue: number
    markedAssetValue: number
    unmarkedAssetValue: number
    totalValue: number
  }
}

interface ApiResponse<T> {
  status: number
  data: T
  message?: string
}

// 响应式数据
const loading = ref(false)
const saving = ref(false)
const historyData = ref<HistoryDataItem[]>([])
const autoSaveEnabled = ref(false)
const INCLUDE_UNMARKED_STORAGE_KEY = 'history_include_unmarked_assets'
const includeUnmarkedAssets = ref(true)  // 考虑非标记资产开关
const USE_STACKED_AREA_STORAGE_KEY = 'history_use_stacked_area'
const useStackedAreaChart = ref(true)  // 使用面积堆叠图开关

// 图表引用
const chartRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null

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

// 从本地存储加载"使用面积堆叠图"设置
const loadUseStackedAreaFromStorage = (): boolean => {
  try {
    const stored = localStorage.getItem(USE_STACKED_AREA_STORAGE_KEY)
    if (stored !== null) {
      return JSON.parse(stored) === true
    }
  } catch (error) {
    console.error('加载"使用面积堆叠图"设置失败:', error)
  }
  return true // 默认值
}

// 保存"使用面积堆叠图"设置到本地存储
const saveUseStackedAreaToStorage = (value: boolean) => {
  try {
    localStorage.setItem(USE_STACKED_AREA_STORAGE_KEY, JSON.stringify(value))
  } catch (error) {
    console.error('保存"使用面积堆叠图"设置失败:', error)
  }
}

// 获取自动保存设置
const fetchAutoSaveSetting = async () => {
  try {
    const response = await http.get('/EVE/home/autoSaveSetting')
    const data = await handleApiResponse<ApiResponse<{ auto_save: boolean }>>(response)
    if (data && data.data) {
      autoSaveEnabled.value = data.data.auto_save
    }
  } catch (error) {
    console.error('获取自动保存设置失败:', error)
  }
}

// 更新自动保存设置
const updateAutoSaveSetting = async (enabled: boolean) => {
  try {
    const response = await http.post('/EVE/home/autoSaveSetting', {
      auto_save: enabled
    })
    const data = await handleApiResponse<ApiResponse<{ message: string; auto_save: boolean }>>(response)
    if (data && data.data) {
      autoSaveEnabled.value = data.data.auto_save
      ElMessage.success(enabled ? '已开启自动保存' : '已关闭自动保存')
    }
  } catch (error) {
    console.error('更新自动保存设置失败:', error)
    ElMessage.error('更新设置失败')
    // 恢复原状态
    autoSaveEnabled.value = !enabled
  }
}

// 保存当日快照
const handleSaveSnapshot = async () => {
  saving.value = true
  try {
    const response = await http.post('/EVE/home/saveSnapshot')
    const data = await handleApiResponse<ApiResponse<{ exists: boolean; message: string }>>(response)

    if (data && data.data) {
      if (data.data.exists) {
        // 今日数据已存在，弹出确认对话框
        try {
          await ElMessageBox.confirm(
            '今日数据已存在，是否覆盖？',
            '确认覆盖',
            {
              confirmButtonText: '覆盖',
              cancelButtonText: '取消',
              type: 'warning'
            }
          )

          // 用户确认覆盖
          const overwriteResponse = await http.put('/EVE/home/saveSnapshot')
          const overwriteData = await handleApiResponse<ApiResponse<{ message: string }>>(overwriteResponse)
          if (overwriteData && overwriteData.data) {
            ElMessage.success(overwriteData.data.message)
            // 刷新历史数据
            await fetchHistoryData()
          }
        } catch (error) {
          // 用户取消
          if (error !== 'cancel') {
            console.error('覆盖快照失败:', error)
            ElMessage.error('覆盖快照失败')
          }
        }
      } else {
        // 保存成功
        ElMessage.success(data.data.message)
        // 刷新历史数据
        await fetchHistoryData()
      }
    }
  } catch (error) {
    console.error('保存快照失败:', error)
    ElMessage.error('保存快照失败')
  } finally {
    saving.value = false
  }
}

// 获取历史数据
const fetchHistoryData = async () => {
  loading.value = true
  try {
    const response = await http.get('/EVE/home/history?days=30')
    const data = await handleApiResponse<ApiResponse<HistoryDataItem[]>>(response)
    if (data && data.data) {
      historyData.value = data.data
      // 等待DOM更新后再更新图表
      await nextTick()
      await updateChart()
    } else {
      historyData.value = []
    }
  } catch (error) {
    console.error('获取历史数据失败:', error)
    ElMessage.error('获取历史数据失败')
    historyData.value = []
  } finally {
    loading.value = false
    // 确保在数据加载完成后初始化图表（即使数据为空）
    await nextTick()
    if (chartRef.value && historyData.value.length > 0 && !chartInstance) {
      chartInstance = echarts.init(chartRef.value)
      const option: EChartsOption = getChartOption()
      chartInstance.setOption(option, true)
    }
  }
}

// 销毁图表
const disposeChart = () => {
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
}

// 获取图表配置
const getChartOption = (): EChartsOption => {
  // 处理数据
  const dates: string[] = []
  const walletValues: number[] = []
  const orderValues: number[] = []
  const runningProcessValues: number[] = []
  const markedAssetValues: number[] = []
  const unmarkedAssetValues: number[] = []

  historyData.value.forEach(item => {
    dates.push(item.date)
    walletValues.push(item.data.walletValue || 0)
    orderValues.push(item.data.orderValue || 0)
    runningProcessValues.push(item.data.runningProcessValue || 0)
    markedAssetValues.push(item.data.markedAssetValue || 0)
    unmarkedAssetValues.push(item.data.unmarkedAssetValue || 0)
  })

  // 定义数据系列配置（包含名称、数据、颜色索引）
  const seriesConfig = [
    { name: '钱包总价值', data: walletValues, colorIndex: 0 },
    { name: '订单总价值', data: orderValues, colorIndex: 1 },
    { name: '运行中流程价值', data: runningProcessValues, colorIndex: 2 },
    { name: '标记资产价值', data: markedAssetValues, colorIndex: 3 }
  ]

  // 如果开关开启，添加非标记资产数据
  if (includeUnmarkedAssets.value) {
    seriesConfig.push({
      name: '非标记资产价值',
      data: unmarkedAssetValues,
      colorIndex: 4
    })
  }

  // 计算每个系列的平均值，用于排序（价值低的在下方）
  const seriesWithAvg = seriesConfig.map(config => {
    const avg = config.data.reduce((sum, val) => sum + val, 0) / config.data.length
    return { ...config, avg }
  })

  // 按平均值从小到大排序（价值低的在下方）
  seriesWithAvg.sort((a, b) => a.avg - b.avg)

  // 构建排序后的 series 数组和 legend 数据
  // 保存所有系列的数据数组，用于计算总和
  const allSeriesData = seriesWithAvg.map(config => config.data)

  const series: any[] = seriesWithAvg.map((config, index) => {
    const isLast = index === seriesWithAvg.length - 1
    const baseConfig: any = {
      name: config.name,
      type: 'line',
      smooth: true,
      emphasis: {
        focus: 'series'
      },
      data: config.data
    }

    // 如果是面积堆叠图
    if (useStackedAreaChart.value) {
      baseConfig.stack = 'Total'
      baseConfig.areaStyle = {}
      if (isLast) {
        baseConfig.label = {
          show: true,
          position: 'top',
          formatter: (params: any) => {
            // 计算所有系列在当前数据点的总和
            const dataIndex = params.dataIndex
            const total = allSeriesData.reduce((sum, seriesData) => {
              return sum + (seriesData[dataIndex] || 0)
            }, 0)
            // 使用 formatNumber 函数进行格式化（千分位分隔）
            return formatNumber(total)
          }
        }
      }
    } else {
      // 普通折线图，不堆叠，不显示面积
      baseConfig.lineStyle = {
        width: 2
      }
    }

    return baseConfig
  })

  const legendData = seriesWithAvg.map(config => config.name)

  // 计算所有数据的最大值和最小值，判断是否需要使用对数坐标
  const allValues = [
    ...walletValues,
    ...orderValues,
    ...runningProcessValues,
    ...markedAssetValues,
    ...(includeUnmarkedAssets.value ? unmarkedAssetValues : [])
  ].filter(v => v > 0) // 过滤掉0值

  let useLogScale = false
  let maxValue = 0
  let minValue = 0

  if (allValues.length > 0) {
    if (useStackedAreaChart.value) {
      // 堆叠图：计算每个时间点的总和，取最大值
      const timePointSums: number[] = []
      for (let i = 0; i < dates.length; i++) {
        const sum = walletValues[i] + orderValues[i] + runningProcessValues[i] + markedAssetValues[i] +
          (includeUnmarkedAssets.value ? unmarkedAssetValues[i] : 0)
        if (sum > 0) {
          timePointSums.push(sum)
        }
      }
      maxValue = timePointSums.length > 0 ? Math.max(...timePointSums) : 0
      minValue = Math.min(...allValues)
    } else {
      // 普通折线图：取单个值的最大值
      maxValue = Math.max(...allValues)
      minValue = Math.min(...allValues)
    }

    const ratio = maxValue / minValue
    // 普通折线图始终使用对数坐标，面积堆叠图在差距超过100倍时使用
    if (!useStackedAreaChart.value) {
      useLogScale = true // 普通折线图始终使用对数坐标
    } else {
      // 如果最大值和最小值差距超过100倍，使用对数坐标
      useLogScale = ratio > 30 && minValue > 0
    }
  }

  // 根据排序后的顺序重新排列颜色
  const colorMap: Record<string, string> = {
    '钱包总价值': '#67c23a',
    '订单总价值': '#e6a23c',
    '运行中流程价值': '#909399',
    '标记资产价值': '#f56c6c',
    '非标记资产价值': '#909399'
  }
  const sortedColors = seriesWithAvg.map(config => colorMap[config.name])

  return {
    // 使用总览页面的颜色主题，按排序后的顺序排列
    color: sortedColors,
    title: {
      text: useStackedAreaChart.value ? '资产价值历史趋势（面积堆叠图）' : '资产价值历史趋势（折线图）'
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        label: {
          backgroundColor: '#6a7985'
        }
      },
      formatter: (params: unknown) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const paramArray = params as Array<{ axisValue: string; marker: string; seriesName: string; value: number }>
        let result = `${paramArray[0].axisValue}<br/>`
        paramArray.forEach((param) => {
          result += `${param.marker}${param.seriesName}: ${formatNumber(param.value)} ISK<br/>`
        })
        // 只有面积堆叠图才显示总计
        if (useStackedAreaChart.value) {
          const total = paramArray.reduce((sum, param) => sum + param.value, 0)
          result += `<br/>总计: ${formatNumber(total)} ISK`
        }
        return result
      }
    },
    legend: {
      data: legendData
    },
    toolbox: {
      feature: {
        saveAsImage: {}
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: [
      {
        type: 'category',
        boundaryGap: false,
        data: dates,
        axisLine: {
          show: true,
          lineStyle: {
            color: '#666',
            width: 1
          }
        },
        splitLine: {
          show: false
        }
      }
    ],
    yAxis: [
      {
        type: useLogScale ? 'log' : 'value',
        ...(useLogScale && {
          logBase: 10,
          ...(allValues.length > 0 && {
            // 对于对数坐标，确保最小值至少为1，避免0值问题
            min: Math.max(1, minValue * 0.9),
            max: maxValue * 1.1 // 留出一些顶部空间
          })
        }),
        axisLine: {
          show: true,
          lineStyle: {
            color: '#666',
            width: 1
          }
        },
        axisTick: {
          show: true,
          lineStyle: {
            color: '#666'
          }
        },
        splitLine: {
          show: true,
          lineStyle: {
            color: '#e0e0e0',
            width: 1,
            type: 'solid'
          }
        },
        axisLabel: {
          formatter: (value: number) => {
            if (value >= 1e9) {
              return `${(value / 1e9).toFixed(1)}B`
            } else if (value >= 1e6) {
              return `${(value / 1e6).toFixed(1)}M`
            } else if (value >= 1e3) {
              return `${(value / 1e3).toFixed(1)}K`
            }
            return value.toFixed(0)
          },
          color: '#666',
          fontSize: 12
        }
      }
    ],
    series: series
  }
}

// 更新图表
const updateChart = async () => {
  await nextTick()
  if (!chartRef.value) return

  // 如果图表实例不存在，先创建
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const option: EChartsOption = getChartOption()
  chartInstance.setOption(option, true)
  chartInstance.resize()
}

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

// 监听开关变化
const handleSwitchChange = () => {
  saveIncludeUnmarkedToStorage(includeUnmarkedAssets.value)
  updateChart()
}

// 监听图表类型开关变化
const handleChartTypeChange = () => {
  saveUseStackedAreaToStorage(useStackedAreaChart.value)
  updateChart()
}

// 监听窗口大小变化
const handleResize = () => {
  if (chartInstance) {
    chartInstance.resize()
  }
}

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  // 从本地存储加载设置
  includeUnmarkedAssets.value = loadIncludeUnmarkedFromStorage()
  useStackedAreaChart.value = loadUseStackedAreaFromStorage()
  await fetchAutoSaveSetting()
  await fetchHistoryData()
})

onUnmounted(() => {
  disposeChart()
  window.removeEventListener('resize', handleResize)
})
</script>

<template>
  <div class="history-container">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-button type="primary" :loading="saving" @click="handleSaveSnapshot">
        保存当日快照
      </el-button>
      <div class="switch-container">
        <span class="switch-label">开启自动保存快照</span>
        <el-switch v-model="autoSaveEnabled" @change="updateAutoSaveSetting" />
      </div>
      <div class="switch-container">
        <span class="switch-label">考虑非标记资产</span>
        <el-switch v-model="includeUnmarkedAssets" @change="handleSwitchChange" />
      </div>
      <div class="switch-container">
        <span class="switch-label">面积堆叠图</span>
        <el-switch v-model="useStackedAreaChart" @change="handleChartTypeChange" />
      </div>
    </div>

    <!-- 图表区域 -->
    <div class="chart-section">
      <el-card shadow="hover">
        <div v-if="loading" class="loading-container">
          <el-empty description="加载中..." :image-size="120" />
        </div>
        <div v-else-if="historyData.length === 0" class="empty-container">
          <el-empty description="暂无历史数据" :image-size="120">
            <el-button type="primary" @click="handleSaveSnapshot">
              保存当日快照
            </el-button>
          </el-empty>
        </div>
        <div v-else ref="chartRef" class="chart"></div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.history-container {
  padding: 20px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding: 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.switch-container {
  display: flex;
  align-items: center;
  gap: 8px;
}

.switch-label {
  font-size: 14px;
  color: #606266;
}

.chart-section {
  margin-top: 20px;
}

.chart {
  width: 100%;
  height: calc(100vh - 450px);
}

.loading-container,
.empty-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 500px;
}

@media (max-width: 768px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .switch-container {
    margin-left: 0;
    justify-content: space-between;
  }
}
</style>
