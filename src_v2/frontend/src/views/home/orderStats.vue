<script setup lang="ts" name="OrderStatsView">
import KTable from '@/components/k/KTable.vue'
import KCard from '@/components/k/KCard.vue'
import KEmpty from '@/components/k/KEmpty.vue'
import KStat from '@/components/k/KStat.vue'
import { ref, onMounted, onUnmounted, nextTick, computed, watch, reactive } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { ElMessage } from 'element-plus'
import { http } from '@/http'
import { handleApiResponse } from '@/utils/apiResponse'
import { getChartThemeColors, themedTooltip, onThemeTokenChange } from '@/utils/echartsTheme'

interface CurrentStats {
  buy_count: number; sell_count: number
  buy_vol: number; sell_vol: number
  buy_isk: number; sell_isk: number
}

interface HistoryRecord {
  period_type: string
  period_start: string
  buy_order_count: number; sell_order_count: number
  buy_volume: number; sell_volume: number
  buy_total_isk: number; sell_total_isk: number
  updated_at: string | null
}

interface DetailItem {
  type_id: number; name_zh: string; name_en: string
  order_count: number; volume: number; total_isk: number
}

interface OrderStatsData { current: CurrentStats; history: HistoryRecord[] }

interface ApiResponse<T> { status: number; data: T; message?: string }

const loading = ref(false)
const periodType = ref<'day' | 'week' | 'month'>('month')
const periods = ref(12)
const chartType = ref<'bar' | 'line'>('bar')
const statsData = ref<OrderStatsData>({
  current: { buy_count: 0, sell_count: 0, buy_vol: 0, sell_vol: 0, buy_isk: 0, sell_isk: 0 },
  history: []
})

const chartRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null
let cleanupThemeWatcher: (() => void) | null = null

const detailLoading = reactive<Record<string, boolean>>({})
const detailData = reactive<Record<string, DetailItem[]>>({})

const periodTotal = computed(() => {
  const h = statsData.value.history
  return {
    buyIsk: h.reduce((s, r) => s + r.buy_total_isk, 0),
    sellIsk: h.reduce((s, r) => s + r.sell_total_isk, 0),
    buyCount: h.reduce((s, r) => s + r.buy_order_count, 0),
    sellCount: h.reduce((s, r) => s + r.sell_order_count, 0),
  }
})

const fetchDetail = async (periodStart: string, isBuy: boolean) => {
  const key = `${periodStart}_${isBuy ? 'buy' : 'sell'}`
  if (detailData[key]) return
  detailLoading[key] = true
  try {
    const res = await http.post('/EVE/home/orderStatsDetail', {
      period_type: periodType.value, period_start: periodStart, is_buy_order: isBuy
    })
    const data = await handleApiResponse<ApiResponse<DetailItem[]>>(res)
    detailData[key] = (data && data.data) ? data.data : []
  } catch {
    console.error('获取订单明细失败')
  } finally {
    delete detailLoading[key]
  }
}

const handleExpandChange = (row: HistoryRecord, expandedRows: HistoryRecord[]) => {
  if (expandedRows.some(r => r.period_start === row.period_start)) {
    fetchDetail(row.period_start, true)
    fetchDetail(row.period_start, false)
  }
}

const getTypeIconUrl = (typeId: number) => `https://images.evetech.net/types/${typeId}/icon?size=32`

const formatIsk = (value: number): string => {
  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(2)}K`
  return `${sign}${abs.toFixed(2)}`
}

const formatVolume = (value: number): string => value ? value.toLocaleString('zh-CN') : '0'

const formatPeriodLabel = (record: HistoryRecord): string => {
  const d = new Date(record.period_start + 'T00:00:00')
  if (record.period_type === 'day') return `${d.getMonth() + 1}/${d.getDate()}`
  if (record.period_type === 'week') {
    const end = new Date(d); end.setDate(end.getDate() + 6)
    return `${d.getMonth() + 1}/${d.getDate()}-${end.getMonth() + 1}/${end.getDate()}`
  }
  return `${d.getFullYear()}/${d.getMonth() + 1}`
}

const fetchData = async () => {
  loading.value = true
  try {
    const res = await http.post('/EVE/home/orderStats', {
      period_type: periodType.value, periods: periods.value
    })
    const data = await handleApiResponse<ApiResponse<OrderStatsData>>(res)
    statsData.value = (data && data.data) ? data.data : {
      current: { buy_count: 0, sell_count: 0, buy_vol: 0, sell_vol: 0, buy_isk: 0, sell_isk: 0 },
      history: []
    }
  } catch {
    ElMessage.error('获取订单统计失败')
  } finally {
    loading.value = false
    if (statsData.value.history.length > 0) {
      await nextTick()
      await updateChart()
    }
  }
}

const disposeChart = () => {
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }
}

const getChartOption = (): EChartsOption => {
  const c = getChartThemeColors()
  const labels: string[] = []
  const buyData: number[] = []
  const sellData: number[] = []
  const netData: number[] = []

  statsData.value.history.forEach(item => {
    labels.push(formatPeriodLabel(item))
    buyData.push(item.buy_total_isk || 0)
    sellData.push(item.sell_total_isk || 0)
    netData.push((item.sell_total_isk || 0) - (item.buy_total_isk || 0))
  })

  const series: any[] = [
    { name: '收购 ISK', type: chartType.value, data: buyData, itemStyle: { color: '#409EFF' }, emphasis: { focus: 'series' } },
    { name: '出售 ISK', type: chartType.value, data: sellData, itemStyle: { color: '#F56C6C' }, emphasis: { focus: 'series' } },
    { name: '净收益', type: 'line', data: netData, itemStyle: { color: '#67C23A' }, lineStyle: { width: 2 }, symbol: 'circle', symbolSize: 6, emphasis: { focus: 'series' } },
  ]

  return {
    tooltip: themedTooltip({
      trigger: 'axis',
      formatter: (params: any) => {
        const arr = Array.isArray(params) ? params : [params]
        let r = `${arr[0]?.axisValue || ''}<br/>`
        arr.forEach((p: any) => { r += `${p.marker}${p.seriesName}: ${formatIsk(p.value)} ISK<br/>` })
        return r
      }
    }),
    legend: {
      data: ['收购 ISK', '出售 ISK', '净收益'],
      textStyle: { color: c.textSecondary }
    },
    toolbox: { feature: { saveAsImage: {} } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: labels, axisLabel: { color: c.textSecondary, rotate: labels.length > 15 ? 30 : 0 }, axisLine: { lineStyle: { color: c.border } } },
    yAxis: { type: 'value', axisLabel: { formatter: (v: number) => formatIsk(v), color: c.textSecondary }, axisLine: { lineStyle: { color: c.border } }, splitLine: { lineStyle: { color: c.border, type: 'solid' } } },
    series
  }
}

const updateChart = async () => {
  await nextTick()
  if (!chartRef.value) return
  if (!chartInstance) chartInstance = echarts.init(chartRef.value)
  chartInstance.setOption(getChartOption(), true)
  chartInstance.resize()
}

const handlePeriodChange = (type: 'day' | 'week' | 'month') => {
  periodType.value = type
  periods.value = type === 'day' ? 30 : 12
  fetchData()
}

let resizeRAF: number | null = null
const handleResize = () => {
  if (resizeRAF !== null) return
  resizeRAF = requestAnimationFrame(() => {
    if (chartInstance) chartInstance.resize()
    resizeRAF = null
  })
}

watch(chartType, () => updateChart())
watch(periodType, () => detailData.__clear ? Object.keys(detailData).forEach(k => delete detailData[k]) : null)

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  cleanupThemeWatcher = onThemeTokenChange(() => updateChart())
  await fetchData()
})

onUnmounted(() => {
  disposeChart()
  if (resizeRAF !== null) cancelAnimationFrame(resizeRAF)
  window.removeEventListener('resize', handleResize)
  cleanupThemeWatcher?.()
  cleanupThemeWatcher = null
})
</script>

<template>
  <div class="order-stats-container">
    <div class="toolbar">
      <div class="toolbar-left">
        <el-radio-group v-model="periodType" @change="handlePeriodChange">
          <el-radio-button value="day">日</el-radio-button>
          <el-radio-button value="week">周</el-radio-button>
          <el-radio-button value="month">月</el-radio-button>
        </el-radio-group>
        <el-radio-group v-model="chartType" size="small" style="margin-left:12px">
          <el-radio-button value="bar">柱状</el-radio-button>
          <el-radio-button value="line">折线</el-radio-button>
        </el-radio-group>
      </div>
      <el-button @click="fetchData" :loading="loading">刷新</el-button>
    </div>

    <div class="summary-cards">
      <KCard class="summary-card">
        <KStat
          :label="`${periodType === 'month' ? '近12月' : periodType === 'week' ? '近12周' : '近30日'}累计收购`"
          :value="periodTotal.buyCount"
          unit="笔"
          :hint="`${formatIsk(periodTotal.buyIsk)} ISK`"
          tone="primary"
          align="center"
        />
      </KCard>
      <KCard class="summary-card">
        <KStat
          :label="`${periodType === 'month' ? '近12月' : periodType === 'week' ? '近12周' : '近30日'}累计出售`"
          :value="periodTotal.sellCount"
          unit="笔"
          :hint="`${formatIsk(periodTotal.sellIsk)} ISK`"
          tone="danger"
          align="center"
        />
      </KCard>
      <KCard class="summary-card">
        <KStat
          label="净收益"
          :value="formatIsk(periodTotal.sellIsk - periodTotal.buyIsk)"
          unit="ISK"
          hint="出售 - 收购"
          :tone="periodTotal.sellIsk - periodTotal.buyIsk >= 0 ? 'success' : 'danger'"
          align="center"
        />
      </KCard>
    </div>

    <div class="chart-section">
      <KCard>
        <div v-if="loading" class="empty-wrap"><KEmpty why="加载中..." size="md" /></div>
        <div v-else-if="statsData.history.length === 0" class="empty-wrap"><KEmpty why="暂无订单统计数据" size="md" /></div>
        <div v-else ref="chartRef" class="chart"></div>
      </KCard>
    </div>

    <div v-if="statsData.history.length > 0" class="table-section">
      <KCard>
        <KTable :data="statsData.history" stripe style="width:100%" max-height="500"
          @expand-change="handleExpandChange" show-summary
          :summary-method="({ columns, data }) => {
            const sums: string[] = ['合计'];
            for (let i = 1; i < columns.length; i++) {
              const prop = columns[i].property as string;
              if (prop === 'buy_order_count') sums.push(String(data.reduce((s:number,r:any) => s + r.buy_order_count, 0)));
              else if (prop === 'sell_order_count') sums.push(String(data.reduce((s:number,r:any) => s + r.sell_order_count, 0)));
              else if (prop === 'buy_total_isk') sums.push(formatIsk(data.reduce((s:number,r:any) => s + r.buy_total_isk, 0)));
              else if (prop === 'sell_total_isk') sums.push(formatIsk(data.reduce((s:number,r:any) => s + r.sell_total_isk, 0)));
              else sums.push('');
            }
            return sums;
          }"
        >
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="expand-content">
                <div v-if="detailLoading[row.period_start + '_buy']" class="detail-loading">加载中...</div>
                <div v-else class="detail-grid">
                  <div class="detail-col">
                    <h4 class="detail-title buy">收购明细</h4>
                    <KTable :data="detailData[row.period_start + '_buy'] || []" size="small" max-height="300">
                      <el-table-column width="40">
                        <template #default="{ row: r }"><img :src="getTypeIconUrl(r.type_id)" alt="" width="32" height="32" style="border-radius:2px" /></template>
                      </el-table-column>
                      <el-table-column label="名称" min-width="160">
                        <template #default="{ row: r }">{{ r.name_zh || r.name_en || `Type ${r.type_id}` }}</template>
                      </el-table-column>
                      <el-table-column label="数量" width="90" align="right">
                        <template #default="{ row: r }">{{ formatVolume(r.volume) }}</template>
                      </el-table-column>
                      <el-table-column label="ISK" width="140" align="right">
                        <template #default="{ row: r }">{{ formatIsk(r.total_isk) }}</template>
                      </el-table-column>
                    </KTable>
                    <div v-if="!detailData[row.period_start + '_buy']?.length" class="detail-empty">无收购记录</div>
                  </div>
                  <div class="detail-col">
                    <h4 class="detail-title sell">出售明细</h4>
                    <KTable :data="detailData[row.period_start + '_sell'] || []" size="small" max-height="300">
                      <el-table-column width="40">
                        <template #default="{ row: r }"><img :src="getTypeIconUrl(r.type_id)" alt="" width="32" height="32" style="border-radius:2px" /></template>
                      </el-table-column>
                      <el-table-column label="名称" min-width="160">
                        <template #default="{ row: r }">{{ r.name_zh || r.name_en || `Type ${r.type_id}` }}</template>
                      </el-table-column>
                      <el-table-column label="数量" width="90" align="right">
                        <template #default="{ row: r }">{{ formatVolume(r.volume) }}</template>
                      </el-table-column>
                      <el-table-column label="ISK" width="140" align="right">
                        <template #default="{ row: r }">{{ formatIsk(r.total_isk) }}</template>
                      </el-table-column>
                    </KTable>
                    <div v-if="!detailData[row.period_start + '_sell']?.length" class="detail-empty">无出售记录</div>
                  </div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="周期" width="180">
            <template #default="{ row }">{{ formatPeriodLabel(row) }}</template>
          </el-table-column>
          <el-table-column label="收购笔数" prop="buy_order_count" width="100" align="right" sortable />
          <el-table-column label="收购 ISK" prop="buy_total_isk" width="160" align="right" sortable>
            <template #default="{ row }">{{ formatIsk(row.buy_total_isk) }}</template>
          </el-table-column>
          <el-table-column label="出售笔数" prop="sell_order_count" width="100" align="right" sortable />
          <el-table-column label="出售 ISK" prop="sell_total_isk" width="160" align="right" sortable>
            <template #default="{ row }">{{ formatIsk(row.sell_total_isk) }}</template>
          </el-table-column>
          <el-table-column label="净收益" width="160" align="right" sortable>
            <template #default="{ row }">
              <span :style="{ color: row.sell_total_isk - row.buy_total_isk >= 0 ? '#67C23A' : '#F56C6C' }">
                {{ formatIsk(row.sell_total_isk - row.buy_total_isk) }}
              </span>
            </template>
          </el-table-column>
        </KTable>
      </KCard>
    </div>
  </div>
</template>

<style scoped>
.order-stats-container { padding: 20px; }

.toolbar {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  margin-bottom: 20px; padding: 16px;
  background: var(--k-color-surface-soft); border-radius: 8px;
  box-shadow: var(--k-shadow-sm); border: 1px solid var(--k-color-border);
}

.summary-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px; }
.summary-card { text-align: center; }

.chart-section { margin-bottom: 20px; }
.chart { width: 100%; height: calc(100vh - 560px); min-height: 350px; }
.empty-wrap { display: flex; justify-content: center; align-items: center; min-height: 400px; }

.table-section { margin-top: 20px; }

.expand-content { padding: 12px 20px; }
.detail-loading { color: var(--k-color-text-secondary); font-size: 14px; padding: 16px 0; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.detail-col { min-width: 0; }
.detail-title { margin: 0 0 8px 0; font-size: 14px; font-weight: 600; }
.detail-title.buy { color: #409EFF; }
.detail-title.sell { color: var(--k-color-danger); }
.detail-empty { text-align: center; color: var(--k-color-text-secondary); font-size: 13px; padding: 16px 0; }

@media (max-width: 768px) {
  .toolbar { flex-direction: column; align-items: stretch; }
  .summary-cards { grid-template-columns: 1fr; }
  .detail-grid { grid-template-columns: 1fr; }
}
/* 卡片/表格已全部走 KCard / KTable + --k-* token，theme.css 负责 EP 基类，
   原先的「Theme override」强制覆盖整段删除。 */
</style>
