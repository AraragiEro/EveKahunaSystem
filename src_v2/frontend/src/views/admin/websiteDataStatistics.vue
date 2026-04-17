<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { http } from '@/http'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { getChartThemeColors, themedTooltip, onThemeTokenChange } from '@/utils/echartsTheme'

const activeTab = ref('calculateHistory')

// 时间范围选择
const daysRange = ref(7) // 默认7天，范围1-30天

// 折线图相关
const hourlyChartRef = ref<HTMLElement>()
let hourlyChartInstance: echarts.ECharts | null = null
const hourlyLoading = ref(false)

// K线图相关
const durationChartRef = ref<HTMLElement>()
let durationChartInstance: echarts.ECharts | null = null
let cleanupThemeWatcher: (() => void) | null = null
const durationLoading = ref(false)

// 用户频率统计相关
const userDaysRange = ref(30) // 默认30天
const userFrequencyLoading = ref(false)
const userFrequencyData = ref<any[]>([])
const selectedUser = ref('')
const userDetailLoading = ref(false)
const userDetailData = ref<any[]>([])
const userDetailDateRange = ref<[Date, Date]>([
  new Date(Date.now() - 30 * 24 * 60 * 60 * 1000), // 30天前
  new Date() // 今天
])
const userDetailChartRef = ref<HTMLElement>()
let userDetailChartInstance: echarts.ECharts | null = null

// 日期快捷选项
const dateShortcuts = [
  {
    text: '最近一周',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 3600 * 1000 * 24 * 7)
      return [start, end]
    }
  },
  {
    text: '最近30天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 3600 * 1000 * 24 * 30)
      return [start, end]
    }
  },
  {
    text: '最近90天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 3600 * 1000 * 24 * 90)
      return [start, end]
    }
  }
]

// 获取每小时统计数据
const fetchHourlyStatistics = async () => {
  hourlyLoading.value = true
  try {
    const res = await http.get(`/admin/statistics/calculateHistory/hourly?days=${daysRange.value}`)
    const data = await res.json()
    
    if (data.status !== 200) {
      ElMessage.error(data.message || '获取统计数据失败')
      return
    }
    
    const statistics = data.data || []
    
    // 生成过去N天的完整小时时间序列（UTC时间）
    // 获取当前UTC时间
    const now = new Date()
    // 计算当前UTC小时的开始时间（去掉分钟、秒、毫秒）
    const currentUTCHour = new Date(Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate(),
      now.getUTCHours(),
      0, 0, 0
    ))
    const endTime = currentUTCHour
    const startTime = new Date(endTime.getTime() - daysRange.value * 24 * 60 * 60 * 1000) // N天前
    
    // 生成完整的时间序列
    const allHours: string[] = []
    const hourMap = new Map<string, { total: number; success: number; failed: number }>()
    
    // 将后端返回的数据映射到Map中
    statistics.forEach((item: any) => {
      hourMap.set(item.hour, {
        total: item.total || 0,
        success: item.success || 0,
        failed: item.failed || 0
      })
    })
    
    // 生成完整的小时时间序列（UTC时间）
    for (let time = new Date(startTime); time <= endTime; time = new Date(time.getTime() + 60 * 60 * 1000)) {
      // 格式化为 'YYYY-MM-DD HH:00:00' 格式（UTC时间）
      const year = time.getUTCFullYear()
      const month = String(time.getUTCMonth() + 1).padStart(2, '0')
      const day = String(time.getUTCDate()).padStart(2, '0')
      const hour = String(time.getUTCHours()).padStart(2, '0')
      const hourStr = `${year}-${month}-${day} ${hour}:00:00`
      allHours.push(hourStr)
    }
    
    // 准备图表数据，填充缺失的时间点为0
    // 转换为时间轴格式：[[timestamp, value], ...]
    const totalData = allHours.map(hour => {
      // 将 'YYYY-MM-DD HH:00:00' 格式转换为Date对象（UTC时间）
      const [datePart, timePart] = hour.split(' ')
      const [year, month, day] = datePart.split('-').map(Number)
      const [hours] = timePart.split(':').map(Number)
      const date = new Date(Date.UTC(year, month - 1, day, hours, 0, 0))
      return [date.getTime(), hourMap.get(hour)?.total || 0]
    })
    const successData = allHours.map(hour => {
      const [datePart, timePart] = hour.split(' ')
      const [year, month, day] = datePart.split('-').map(Number)
      const [hours] = timePart.split(':').map(Number)
      const date = new Date(Date.UTC(year, month - 1, day, hours, 0, 0))
      return [date.getTime(), hourMap.get(hour)?.success || 0]
    })
    const failedData = allHours.map(hour => {
      const [datePart, timePart] = hour.split(' ')
      const [year, month, day] = datePart.split('-').map(Number)
      const [hours] = timePart.split(':').map(Number)
      const date = new Date(Date.UTC(year, month - 1, day, hours, 0, 0))
      return [date.getTime(), hourMap.get(hour)?.failed || 0]
    })
    
    // 更新折线图
    if (hourlyChartInstance) {
      const c = getChartThemeColors()
      // 根据选择的天数生成标题
      const titleText = daysRange.value === 1 
        ? '过去1天每小时计算统计'
        : daysRange.value === 7
        ? '过去一周每小时计算统计'
        : daysRange.value === 30
        ? '过去一月每小时计算统计'
        : `过去${daysRange.value}天每小时计算统计`
      
      const option: EChartsOption = {
        title: {
          text: titleText,
          left: 'center',
          top: 10,
          textStyle: { color: c.text }
        },
        tooltip: {
          ...themedTooltip(c),
          trigger: 'axis',
          axisPointer: {
            type: 'cross'
          },
          formatter: (params: any) => {
            if (Array.isArray(params) && params.length > 0) {
              const param = params[0]
              // 时间轴模式下，param.value[0] 是时间戳
              if (param.value && Array.isArray(param.value) && param.value.length >= 2) {
                const timestamp = param.value[0]
                const date = convertUTCToUTC8(new Date(timestamp))
                const timeStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:00`
                
                let result = `<div style="margin-bottom: 5px;"><strong>${timeStr}</strong></div>`
                params.forEach((item: any) => {
                  const value = Array.isArray(item.value) ? item.value[1] : item.value
                  result += `<div>${item.marker}${item.seriesName}: <strong>${value}</strong></div>`
                })
                return result
              }
            }
            return ''
          }
        },
        legend: {
          data: ['启动数量', '成功数量', '失败数量'],
          top: 35
        },
        grid: {
          left: '3%',
          right: '4%',
          bottom: '15%', // 为底部滑块留出空间
          top: '15%',
          containLabel: true
        },
        dataZoom: [
          {
            type: 'inside', // 内置型数据区域缩放组件
            start: 0,
            end: 100
          },
          {
            type: 'slider', // 滑动条型数据区域缩放组件
            start: 0,
            end: 100,
            height: 40,
            bottom: 10,
            handleIcon: 'path://M30.9,53.2C16.8,53.2,5.3,41.7,5.3,27.6S16.8,2,30.9,2C45,2,56.4,13.5,56.4,27.6S45,53.2,30.9,53.2z M30.9,3.5C17.6,3.5,6.8,14.4,6.8,27.6c0,13.3,10.8,24.1,24.1,24.1C44.2,51.7,55,40.9,55,27.6C54.9,14.4,44.1,3.5,30.9,3.5z M36.9,35.8c0,0.6-0.4,1-1,1H26.8c-0.6,0-1-0.4-1-1V19.4c0-0.6,0.4-1,1-1h9.2c0.6,0,1,0.4,1,1V35.8z',
            handleSize: '80%',
            handleStyle: {
              color: c.surface,
              shadowBlur: 3,
              shadowColor: 'rgba(0, 0, 0, 0.6)',
              shadowOffsetX: 2,
              shadowOffsetY: 2
            },
            labelFormatter: (value: number) => {
              // 将时间戳转换为UTC+8时间显示
              const date = convertUTCToUTC8(new Date(value))
              return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:00`
            }
          }
        ],
        xAxis: {
          type: 'time',
          axisLine: { lineStyle: { color: c.border } },
          axisTick: { lineStyle: { color: c.border } },
          boundaryGap: [0, 0], // time类型使用数组格式
          axisLabel: {
            color: c.textSecondary,
            formatter: (value: number) => {
              // 将UTC时间转换为UTC+8并格式化显示
              const date = convertUTCToUTC8(new Date(value))
              return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:00`
            }
          }
        },
        yAxis: {
          type: 'value',
          name: '数量'
        },
        series: [
          {
            name: '启动数量',
            type: 'line',
            data: totalData,
            itemStyle: { color: c.primary },
            smooth: true,
            symbol: 'none' // 不显示数据点，使线条更平滑
          },
          {
            name: '成功数量',
            type: 'line',
            data: successData,
            itemStyle: { color: c.success },
            smooth: true,
            symbol: 'none'
          },
          {
            name: '失败数量',
            type: 'line',
            data: failedData,
            itemStyle: { color: c.danger },
            smooth: true,
            symbol: 'none'
          }
        ]
      }
      
      hourlyChartInstance.setOption(option, true)
    }
  } catch (error: any) {
    ElMessage.error('获取每小时统计数据失败')
    console.error(error)
  } finally {
    hourlyLoading.value = false
  }
}

// 获取完成时间区间统计数据
const fetchDurationStatistics = async () => {
  durationLoading.value = true
  try {
    const res = await http.get('/admin/statistics/calculateHistory/duration')
    const data = await res.json()
    
    if (data.status !== 200) {
      ElMessage.error(data.message || '获取统计数据失败')
      return
    }
    
    const statistics = data.data || []
    
    // 调试信息
    console.log('Duration statistics data:', statistics)
    
    if (statistics.length === 0) {
      // 如果没有数据，显示空图表
      if (durationChartInstance) {
        durationChartInstance.setOption({
          title: {
            text: '完成时间区间统计（按任务数量）',
            left: 'center'
          },
          graphic: {
            type: 'text',
            left: 'center',
            top: 'middle',
            style: {
              text: '暂无数据',
              fontSize: 16,
              fill: '#909399'
            }
          }
        }, true)
      }
      return
    }
    
    // 过滤和排序数据，确保product_count有效（包括0）
    const validStatistics = statistics
      .filter((item: any) => {
        // 允许product_count为0，但不允许null或undefined
        return item.product_count != null && item.product_count !== undefined && 
               item.min_duration != null && item.max_duration != null && item.avg_duration != null
      })
      .sort((a: any, b: any) => {
        // 按product_count排序，确保是数字比较
        const countA = Number(a.product_count) || 0
        const countB = Number(b.product_count) || 0
        return countA - countB
      })
    
    if (validStatistics.length === 0) {
      ElMessage.warning('没有有效的任务数量数据')
      return
    }
    
    // 准备K线图数据
    // K线图数据格式: [开盘, 收盘, 最低, 最高]
    // 对于时间区间统计，我们使用: [最小值, 最大值, 最小值, 最大值]
    // 但更好的方式是使用: [平均值, 平均值, 最小值, 最大值] 来显示区间
    const candlestickData = validStatistics.map((item: any) => {
      // 确保数据有效
      if (item.min_duration == null || item.max_duration == null || item.avg_duration == null) {
        console.warn('Invalid duration data:', item)
        return [0, 0, 0, 0]
      }
      // K线图格式: [开盘, 收盘, 最低, 最高]
      // 使用平均值作为开盘和收盘，最小值和最大值作为最低和最高
      // 这样K线图会显示一个从最小值到最大值的区间，中间线是平均值
      return [
        item.avg_duration,  // 开盘（使用平均值）
        item.avg_duration,  // 收盘（使用平均值）
        item.min_duration,  // 最低（最小值）
        item.max_duration   // 最高（最大值）
      ]
    })
    
    // 确保categories是有效的字符串数组，按product_count排序
    const categories = validStatistics.map((item: any) => {
      return String(item.product_count)
    })
    
    // 调试信息
    console.log('Valid statistics:', validStatistics)
    console.log('Categories:', categories)
    console.log('Candlestick data:', candlestickData)
    
    // 更新K线图
    if (durationChartInstance) {
      const c = getChartThemeColors()
      const option: EChartsOption = {
        title: {
          text: '完成时间区间统计（按任务数量）',
          left: 'center',
          top: 10,
          textStyle: { color: c.text }
        },
        tooltip: {
          ...themedTooltip(c),
          trigger: 'axis',
          axisPointer: {
            type: 'cross'
          },
          formatter: (params: any) => {
            if (Array.isArray(params) && params.length > 0) {
              const param = params[0]
              const index = param.dataIndex
              if (index >= 0 && index < validStatistics.length) {
                const stat = validStatistics[index]
                return `
                  <div>
                    <div><strong>任务数量:</strong> ${stat.product_count}</div>
                    <div><strong>样本数:</strong> ${stat.count}</div>
                    <div><strong>最小耗时:</strong> ${formatDuration(stat.min_duration)}</div>
                    <div><strong>最大耗时:</strong> ${formatDuration(stat.max_duration)}</div>
                    <div><strong>平均耗时:</strong> ${formatDuration(stat.avg_duration)}</div>
                  </div>
                `
              }
            }
            return ''
          }
        },
        legend: {
          data: ['完成时间区间'],
          top: 35,
          textStyle: { color: c.textSecondary }
        },
        grid: {
          left: '3%',
          right: '4%',
          bottom: '3%',
          top: '15%',
          containLabel: true
        },
        xAxis: {
          type: 'category',
          axisLine: { lineStyle: { color: c.border } },
          axisTick: { lineStyle: { color: c.border } },
          data: categories,
          name: '任务数量',
          nameLocation: 'middle',
          nameGap: 30,
          axisLabel: {
            color: c.textSecondary,
            rotate: categories.length > 20 ? 45 : 0,  // 如果数据点多，旋转标签
            interval: categories.length > 30 ? 'auto' : 0  // 如果数据点太多，自动间隔显示
          }
        },
        yAxis: {
          type: 'value',
          name: '完成时间（秒）',
          axisLabel: {
            color: c.textSecondary,
            formatter: (value: number) => {
              return formatDuration(value)
            }
          }
        },
        series: [
          {
            name: '完成时间区间',
            type: 'candlestick',
            data: candlestickData,
            itemStyle: {
              color: c.success,  // 上涨颜色（收盘>=开盘）
              color0: c.success,  // 由于我们使用平均值作为开盘和收盘，所以颜色相同
              borderColor: c.success,
              borderColor0: c.success
            },
            // 使用平均值作为开盘和收盘，最小值和最大值作为最低和最高
            // 这样K线图会显示一个从最小值到最大值的区间，中间线是平均值
          }
        ]
      }
      
      durationChartInstance.setOption(option, true)
    }
  } catch (error: any) {
    ElMessage.error('获取完成时间区间统计数据失败')
    console.error(error)
  } finally {
    durationLoading.value = false
  }
}

// UTC时间转换为UTC+8
const convertUTCToUTC8 = (utcTime: string | Date): Date => {
  const date = typeof utcTime === 'string' ? new Date(utcTime) : utcTime
  // UTC时间加上8小时转换为UTC+8
  return new Date(date.getTime() + 8 * 60 * 60 * 1000)
}

// 格式化持续时间显示
const formatDuration = (seconds: number): string => {
  if (seconds < 60) {
    return `${seconds.toFixed(1)}秒`
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${minutes}分${secs.toFixed(0)}秒`
  } else {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return `${hours}小时${minutes}分`
  }
}

// 获取用户频率统计
const fetchUserFrequencyStatistics = async () => {
  userFrequencyLoading.value = true
  try {
    const res = await http.get(`/admin/statistics/calculateHistory/userFrequency?days=${userDaysRange.value}&limit=100`)
    const data = await res.json()
    
    if (data.status !== 200) {
      ElMessage.error(data.message || '获取用户频率统计失败')
      return
    }
    
    userFrequencyData.value = data.data || []
  } catch (error: any) {
    ElMessage.error('获取用户频率统计失败')
    console.error(error)
  } finally {
    userFrequencyLoading.value = false
  }
}

// 获取特定用户计算详情
const fetchUserDetail = async () => {
  if (!selectedUser.value) {
    ElMessage.warning('请先选择一个用户')
    return
  }
  
  userDetailLoading.value = true
  try {
    const startDate = userDetailDateRange.value[0].toISOString().slice(0, 19)
    const endDate = userDetailDateRange.value[1].toISOString().slice(0, 19)
    
    const res = await http.get(`/admin/statistics/calculateHistory/userDetail?user_name=${selectedUser.value}&start_date=${startDate}&end_date=${endDate}`)
    const data = await res.json()
    
    if (data.status !== 200) {
      ElMessage.error(data.message || '获取用户计算详情失败')
      return
    }
    
    userDetailData.value = data.data || []
    updateUserDetailChart()
  } catch (error: any) {
    ElMessage.error('获取用户计算详情失败')
    console.error(error)
  } finally {
    userDetailLoading.value = false
  }
}

// 更新用户详情图表
const updateUserDetailChart = () => {
  if (!userDetailChartInstance) return
  
  const c = getChartThemeColors()
  
  // 按日期分组统计
  const dailyStats: Record<string, { total: number; success: number; failed: number }> = {}
  
  userDetailData.value.forEach((item: any) => {
    if (!item.calculate_start_time) return
    
    const date = item.calculate_start_time.slice(0, 10) // YYYY-MM-DD
    if (!dailyStats[date]) {
      dailyStats[date] = { total: 0, success: 0, failed: 0 }
    }
    
    dailyStats[date].total += 1
    if (item.is_success) {
      dailyStats[date].success += 1
    } else {
      dailyStats[date].failed += 1
    }
  })
  
  // 排序日期
  const sortedDates = Object.keys(dailyStats).sort()
  
  const option: EChartsOption = {
    title: {
      text: `${selectedUser.value} 的计算使用频率`,
      left: 'center',
      top: 10,
      textStyle: { color: c.text }
    },
    tooltip: {
      ...themedTooltip(c),
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: ['总次数', '成功次数', '失败次数'],
      top: 35
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '10%',
      top: '20%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: sortedDates,
      axisLine: { lineStyle: { color: c.border } },
      axisTick: { lineStyle: { color: c.border } },
      axisLabel: { color: c.textSecondary }
    },
    yAxis: {
      type: 'value',
      name: '次数',
      minInterval: 1
    },
    series: [
      {
        name: '总次数',
        type: 'bar',
        data: sortedDates.map(date => dailyStats[date].total),
        itemStyle: { color: c.primary }
      },
      {
        name: '成功次数',
        type: 'bar',
        data: sortedDates.map(date => dailyStats[date].success),
        itemStyle: { color: c.success }
      },
      {
        name: '失败次数',
        type: 'bar',
        data: sortedDates.map(date => dailyStats[date].failed),
        itemStyle: { color: c.danger }
      }
    ]
  }
  
  userDetailChartInstance.setOption(option, true)
}

// 初始化用户详情图表
const initUserDetailChart = async () => {
  await nextTick()
  if (userDetailChartRef.value && !userDetailChartInstance) {
    userDetailChartInstance = echarts.init(userDetailChartRef.value)
    window.addEventListener('resize', () => {
      userDetailChartInstance?.resize()
    })
  }
}

// 监听用户时间范围变化
const handleUserDaysRangeChange = (value: number) => {
  fetchUserFrequencyStatistics()
}

// 选择用户查看详情
const handleSelectUser = (userName: string) => {
  selectedUser.value = userName
  // 设置默认时间范围为最近30天
  userDetailDateRange.value = [
    new Date(Date.now() - 30 * 24 * 60 * 60 * 1000),
    new Date()
  ]
  fetchUserDetail()
}

// 监听用户详情时间范围变化
const handleUserDetailDateRangeChange = () => {
  fetchUserDetail()
}

// 格式化日期时间显示
const formatDateTime = (dateTimeStr: string): string => {
  if (!dateTimeStr) return '-'
  const date = new Date(dateTimeStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}


// 初始化折线图
const initHourlyChart = async () => {
  await nextTick()
  if (hourlyChartRef.value && !hourlyChartInstance) {
    hourlyChartInstance = echarts.init(hourlyChartRef.value)
    window.addEventListener('resize', () => {
      hourlyChartInstance?.resize()
    })
  }
  await fetchHourlyStatistics()
}

// 初始化K线图
const initDurationChart = async () => {
  await nextTick()
  if (durationChartRef.value && !durationChartInstance) {
    durationChartInstance = echarts.init(durationChartRef.value)
    window.addEventListener('resize', () => {
      durationChartInstance?.resize()
    })
  }
  await fetchDurationStatistics()
}

// 监听时间范围变化
const handleDaysRangeChange = (value: number) => {
  // v-model会自动更新daysRange.value，这里直接使用传入的value
  fetchHourlyStatistics()
}

// 监听标签页切换
const handleTabChange = (tabName: string) => {
if (tabName === 'calculateHistory') {
setTimeout(() => {
initHourlyChart()
initDurationChart()
}, 100)
  } else if (tabName === 'userFrequency') {
    setTimeout(() => {
      fetchUserFrequencyStatistics()
      initUserDetailChart()
}, 100)
  }
}

const refreshChartsByTheme = () => {
  if (activeTab.value !== 'calculateHistory') return
  if (hourlyChartInstance) {
    fetchHourlyStatistics()
  }
  if (durationChartInstance) {
    fetchDurationStatistics()
  }
}

onMounted(() => {
  cleanupThemeWatcher = onThemeTokenChange(() => {
    refreshChartsByTheme()
  })
  if (activeTab.value === 'calculateHistory') {
    setTimeout(() => {
      initHourlyChart()
      initDurationChart()
    }, 100)
  }
})

onUnmounted(() => {
  cleanupThemeWatcher?.()
  cleanupThemeWatcher = null
  if (hourlyChartInstance) {
    hourlyChartInstance.dispose()
    hourlyChartInstance = null
  }
  if (durationChartInstance) {
    durationChartInstance.dispose()
    durationChartInstance = null
  }
  window.removeEventListener('resize', () => {
    hourlyChartInstance?.resize()
    durationChartInstance?.resize()
  })
})
</script>

<template>
  <div class="website-data-statistics">
    <el-tabs v-model="activeTab" @tab-change="handleTabChange" class="statistics-tabs">
      <!-- 计算历史行为数据展示 -->
      <el-tab-pane label="计算历史行为数据" name="calculateHistory">
        <div class="chart-container">
          <!-- 时间范围选择器 -->
          <div class="range-selector">
            <div class="range-label">时间范围：</div>
            <el-slider
              v-model="daysRange"
              :min="1"
              :max="30"
              :step="1"
              show-stops
              :show-tooltip="true"
              :format-tooltip="(val: number) => `${val}天`"
              @change="handleDaysRangeChange"
              style="flex: 1; margin: 0 20px;"
            />
            <div class="range-value">{{ daysRange }}天</div>
          </div>
          
          <!-- 每小时统计折线图 -->
          <div class="chart-wrapper">
            <div 
              ref="hourlyChartRef" 
              class="chart" 
              v-loading="hourlyLoading"
            ></div>
          </div>
          
          <!-- 完成时间区间K线图 -->
          <div class="chart-wrapper">
            <div 
              ref="durationChartRef" 
              class="chart" 
              v-loading="durationLoading"
            ></div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 用户频率统计 -->
      <el-tab-pane label="用户频率统计" name="userFrequency">
        <div class="user-frequency-container">
          <!-- 时间范围选择器 -->
          <div class="range-selector">
            <div class="range-label">统计时间范围：</div>
            <el-slider
              v-model="userDaysRange"
              :min="1"
              :max="90"
              :step="1"
              show-stops
              :show-tooltip="true"
              :format-tooltip="(val: number) => `${val}天`"
              @change="handleUserDaysRangeChange"
              style="flex: 1; margin: 0 20px;"
            />
            <div class="range-value">{{ userDaysRange }}天</div>
          </div>
          
          <div class="user-frequency-content">
            <!-- 左侧用户列表 -->
            <div class="user-list-section" v-loading="userFrequencyLoading">
              <div class="section-title">高频用户排行 (Top {{ userFrequencyData.length }})</div>
              <el-table
                :data="userFrequencyData"
                style="width: 100%"
                height="500"
                highlight-current-row
                @row-click="(row: any) => handleSelectUser(row.user_name)"
                :row-class-name="(row: any) => row.user_name === selectedUser ? 'selected-row' : ''"
              >
                <el-table-column type="index" label="排名" width="70" align="center">
                  <template #default="{ $index }">
                    <el-tag
                      :type="$index < 3 ? 'danger' : $index < 10 ? 'warning' : 'info'"
                      effect="dark"
                      size="small"
                    >
                      {{ $index + 1 }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="user_name" label="用户名" min-width="120" show-overflow-tooltip />
                <el-table-column prop="total_count" label="总次数" width="100" align="center" sortable />
                <el-table-column prop="success_count" label="成功" width="80" align="center">
                  <template #default="{ row }">
                    <span style="color: var(--el-color-success)">{{ row.success_count }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="failed_count" label="失败" width="80" align="center">
                  <template #default="{ row }">
                    <span style="color: var(--el-color-danger)">{{ row.failed_count }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="成功率" width="90" align="center">
                  <template #default="{ row }">
                    <el-tag
                      :type="row.total_count > 0 && row.success_count / row.total_count >= 0.9 ? 'success' : 'warning'"
                      size="small"
                    >
                      {{ row.total_count > 0 ? ((row.success_count / row.total_count) * 100).toFixed(1) : '0.0' }}%
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
            
            <!-- 右侧用户详情 -->
            <div class="user-detail-section" v-if="selectedUser">
              <div class="section-title">{{ selectedUser }} 的计算详情</div>
              
              <!-- 时间范围选择 -->
              <div class="detail-date-range">
                <span class="detail-label">查询时间范围：</span>
                <el-date-picker
                  v-model="userDetailDateRange"
                  type="daterange"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  :shortcuts="dateShortcuts"
                  @change="handleUserDetailDateRangeChange"
                  size="small"
                />
              </div>
              
              <!-- 用户详情图表 -->
              <div class="user-detail-chart-wrapper" v-loading="userDetailLoading">
                <div ref="userDetailChartRef" class="user-detail-chart"></div>
              </div>
              
              <!-- 用户详情表格 -->
              <div class="user-detail-table" v-loading="userDetailLoading">
                <el-table
                  :data="userDetailData"
                  style="width: 100%"
                  height="250"
                  size="small"
                >
                  <el-table-column type="index" label="#" width="50" align="center" />
                  <el-table-column prop="plan_name" label="计划名称" min-width="120" show-overflow-tooltip />
                  <el-table-column prop="product_count" label="产品数" width="80" align="center" />
                  <el-table-column prop="calculate_start_time" label="开始时间" width="150" align="center">
                    <template #default="{ row }">
                      {{ formatDateTime(row.calculate_start_time) }}
                    </template>
                  </el-table-column>
                  <el-table-column prop="is_success" label="状态" width="80" align="center">
                    <template #default="{ row }">
                      <el-tag :type="row.is_success ? 'success' : 'danger'" size="small">
                        {{ row.is_success ? '成功' : '失败' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
            
            <!-- 未选择用户时的提示 -->
            <div class="user-detail-section empty" v-else>
              <el-empty description="点击左侧用户查看详情" />
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.website-data-statistics {
  padding: 20px;
}

.statistics-tabs {
  min-height: 600px;
}

.chart-container {
  display: flex;
  flex-direction: column;
  gap: 30px;
  margin-top: 20px;
}

.range-selector {
  display: flex;
  align-items: center;
  background: var(--k-color-surface);
  padding: 20px;
  border-radius: 4px;
  box-shadow: var(--k-shadow-md);
  margin-bottom: 10px;
  border: 1px solid var(--k-color-border);
}

.range-label {
  font-size: 14px;
  color: var(--k-color-text-secondary);
  font-weight: 500;
  min-width: 80px;
}

.range-value {
  font-size: 14px;
  color: var(--k-color-primary);
  font-weight: 600;
  min-width: 50px;
  text-align: right;
}

.chart-wrapper {
  width: 100%;
  height: 500px;
  background: var(--k-color-surface);
  border-radius: 4px;
  box-shadow: var(--k-shadow-md);
  border: 1px solid var(--k-color-border);
  padding: 20px;
  box-sizing: border-box;
}

.chart {
  width: 100%;
  height: 100%;
  min-height: 400px;
}

/* 用户频率统计样式 */
.user-frequency-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 20px;
}

.user-frequency-content {
  display: flex;
  gap: 20px;
  height: calc(100vh - 300px);
  min-height: 600px;
}

.user-list-section {
  flex: 0 0 450px;
  background: var(--k-color-surface);
  border-radius: 4px;
  box-shadow: var(--k-shadow-md);
  border: 1px solid var(--k-color-border);
  padding: 20px;
  overflow: auto;
}

.user-detail-section {
  flex: 1;
  background: var(--k-color-surface);
  border-radius: 4px;
  box-shadow: var(--k-shadow-md);
  border: 1px solid var(--k-color-border);
  padding: 20px;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.user-detail-section.empty {
  display: flex;
  align-items: center;
  justify-content: center;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--k-color-text);
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--k-color-border);
}

.detail-date-range {
  display: flex;
  align-items: center;
  margin-bottom: 15px;
  gap: 10px;
}

.detail-label {
  font-size: 14px;
  color: var(--k-color-text-secondary);
  white-space: nowrap;
}

.user-detail-chart-wrapper {
  height: 300px;
  margin-bottom: 15px;
  background: var(--k-color-background);
  border-radius: 4px;
  padding: 10px;
}

.user-detail-chart {
  width: 100%;
  height: 100%;
}

.user-detail-table {
  flex: 1;
  overflow: auto;
}

:deep(.selected-row) {
  background-color: var(--el-color-primary-light-9) !important;
}

:deep(.el-table__row) {
  cursor: pointer;
}

@media (max-width: 1200px) {
  .user-frequency-content {
    flex-direction: column;
  }
  
  .user-list-section {
    flex: none;
    height: 400px;
  }
  
  .user-detail-section {
    flex: none;
    height: 600px;
  }
}

@media (max-width: 768px) {
  .user-list-section,
  .user-detail-section {
    padding: 10px;
  }
  
  .user-detail-chart-wrapper {
    height: 250px;
  }
}

@media (max-width: 768px) {
  .chart-wrapper {
    height: 400px;
  }
  
  .chart {
    min-height: 300px;
  }
}
</style>

