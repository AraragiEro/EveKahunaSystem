<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { http } from '@/http'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'

const activeTab = ref('calculateHistory')

// 折线图相关
const hourlyChartRef = ref<HTMLElement>()
let hourlyChartInstance: echarts.ECharts | null = null
const hourlyLoading = ref(false)

// K线图相关
const durationChartRef = ref<HTMLElement>()
let durationChartInstance: echarts.ECharts | null = null
const durationLoading = ref(false)

// 获取每小时统计数据
const fetchHourlyStatistics = async () => {
  hourlyLoading.value = true
  try {
    const res = await http.get('/admin/statistics/calculateHistory/hourly?days=7')
    const data = await res.json()
    
    if (data.status !== 200) {
      ElMessage.error(data.message || '获取统计数据失败')
      return
    }
    
    const statistics = data.data || []
    
    // 准备图表数据
    const hours = statistics.map((item: any) => item.hour)
    const totalData = statistics.map((item: any) => item.total)
    const successData = statistics.map((item: any) => item.success)
    const failedData = statistics.map((item: any) => item.failed)
    
    // 更新折线图
    if (hourlyChartInstance) {
      const option: EChartsOption = {
        title: {
          text: '过去一周每小时计算统计',
          left: 'center',
          top: 10
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'cross'
          }
        },
        legend: {
          data: ['启动数量', '成功数量', '失败数量'],
          top: 35
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
          boundaryGap: false,
          data: hours,
          axisLabel: {
            rotate: 45,
            formatter: (value: string) => {
              // 将UTC时间转换为UTC+8并格式化显示
              const date = convertUTCToUTC8(value)
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
            itemStyle: { color: '#5470c6' },
            smooth: true
          },
          {
            name: '成功数量',
            type: 'line',
            data: successData,
            itemStyle: { color: '#91cc75' },
            smooth: true
          },
          {
            name: '失败数量',
            type: 'line',
            data: failedData,
            itemStyle: { color: '#ee6666' },
            smooth: true
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
              fill: '#999'
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
      const option: EChartsOption = {
        title: {
          text: '完成时间区间统计（按任务数量）',
          left: 'center',
          top: 10
        },
        tooltip: {
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
          top: 35
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
          data: categories,
          name: '任务数量',
          nameLocation: 'middle',
          nameGap: 30,
          axisLabel: {
            rotate: categories.length > 20 ? 45 : 0,  // 如果数据点多，旋转标签
            interval: categories.length > 30 ? 'auto' : 0  // 如果数据点太多，自动间隔显示
          }
        },
        yAxis: {
          type: 'value',
          name: '完成时间（秒）',
          axisLabel: {
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
              color: '#26a69a',  // 上涨颜色（收盘>=开盘）
              color0: '#26a69a',  // 由于我们使用平均值作为开盘和收盘，所以颜色相同
              borderColor: '#26a69a',
              borderColor0: '#26a69a'
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

// 监听标签页切换
const handleTabChange = (tabName: string) => {
  if (tabName === 'calculateHistory') {
    setTimeout(() => {
      initHourlyChart()
      initDurationChart()
    }, 100)
  }
}

onMounted(() => {
  if (activeTab.value === 'calculateHistory') {
    setTimeout(() => {
      initHourlyChart()
      initDurationChart()
    }, 100)
  }
})

onUnmounted(() => {
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

.chart-wrapper {
  width: 100%;
  height: 500px;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  padding: 20px;
  box-sizing: border-box;
}

.chart {
  width: 100%;
  height: 100%;
  min-height: 400px;
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

