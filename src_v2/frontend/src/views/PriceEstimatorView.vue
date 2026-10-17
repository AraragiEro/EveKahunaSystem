<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { http } from '@/http'
import { ElMessage } from 'element-plus'

// ======================= 类型定义 =====================
interface EstimateItem {
  name: string
  name_en: string
  type_id: number | null
  quantity: number
  has_blueprint: boolean
  cost_cached: boolean
  jita_buy: number
  jita_sell: number
  jita_mid: number
  frt_buy: number
  frt_sell: number
  cost: number
  total_jita_buy: number
  total_jita_sell: number
  total_frt_sell: number
  total_cost: number
}

interface EstimateSummary {
  total_jita_buy: number
  total_jita_sell: number
  total_frt_sell: number
  total_cost: number
  coefficient: number
}

interface EstimateResult {
  text?: string
  coefficient?: number
  items: EstimateItem[]
  missing_cost_type_ids: number[]
  unrecognized_names: string[]
  summary: EstimateSummary
}

// ======================= 状态 =====================
const inputText = ref('')
const coefficient = ref(1.0)
const loading = ref(false)
const calculatingCost = ref(false)
const estimateResult = ref<EstimateResult | null>(null)

// 成本计算进度
const progressVisible = ref(false)
const progressPercent = ref(0)
const progressStep = ref('')
const progressTotal = ref(0)
const progressCompleted = ref(0)
let progressTimer: ReturnType<typeof setInterval> | null = null

const route = useRoute()
const router = useRouter()

let lastEstimatedText = ''
let lastEstimatedCoefficient = 1.0

// 页面加载时检查 URL 中的 uuid 参数
onMounted(async () => {
  const uuid = route.query.uuid as string | undefined
  if (uuid) {
    loading.value = true
    try {
      const res = await http.get(`/EVE/price-estimator/result?uuid=${uuid}`)
      const data = await res.json()
      if (data.status === 200) {
        estimateResult.value = data.data
        // 还原原始文本和系数
        if (data.data.text) {
          inputText.value = data.data.text
          lastEstimatedText = data.data.text
        }
        if (data.data.coefficient) {
          coefficient.value = data.data.coefficient
          lastEstimatedCoefficient = data.data.coefficient
        }
      } else {
        ElMessage.warning(data.message || '估价结果已过期')
      }
    } catch {
      ElMessage.error('加载分享的估价结果失败')
    } finally {
      loading.value = false
    }
  }
})

const showCalculateCostButton = computed(() =>
  (estimateResult.value?.missing_cost_type_ids?.length ?? 0) > 0
)

const priceCards = computed(() => {
  if (!estimateResult.value) return []
  const s = estimateResult.value.summary
  return [
    { label: 'Jita卖总价', value: s.total_jita_sell, display: formatAccounting(s.total_jita_sell) },
    { label: 'Jita买总价', value: s.total_jita_buy, display: formatAccounting(s.total_jita_buy) },
    { label: '4H卖总价', value: s.total_frt_sell, display: formatAccounting(s.total_frt_sell) },
    { label: '成本总价', value: s.total_cost, display: formatAccounting(s.total_cost) },
    { label: '调整后Jita卖', value: s.total_jita_sell * coefficient.value, display: formatAccounting(s.total_jita_sell * coefficient.value), accent: true },
    { label: '调整后Jita买', value: s.total_jita_buy * coefficient.value, display: formatAccounting(s.total_jita_buy * coefficient.value), accent: true },
    { label: '调整后4H卖', value: s.total_frt_sell * coefficient.value, display: formatAccounting(s.total_frt_sell * coefficient.value), accent: true },
    { label: '调整后成本', value: s.total_cost * coefficient.value, display: formatAccounting(s.total_cost * coefficient.value), accent: true },
  ]
})

// ======================= 金额格式化 =====================
function formatAccounting(value: number): string {
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

// 降级：本地更新成本（当无法从服务端重新加载时使用）
function patchCostLocal(prog: { calculated?: Record<string, { cost: number }> }) {
  if (!estimateResult.value || !prog.calculated) return
  const calculated = prog.calculated
  for (const item of estimateResult.value.items) {
    if (item.type_id === null) continue
    const tidStr = String(item.type_id)
    if (calculated[tidStr]) {
      item.cost = calculated[tidStr].cost
      item.cost_cached = true
      item.total_cost = Math.round(item.cost * item.quantity * 100) / 100
    }
  }
  const items = estimateResult.value.items
  const summary = estimateResult.value.summary
  summary.total_cost = items.reduce((s, i) => s + i.total_cost, 0)
  summary.total_cost = Math.round(summary.total_cost * 100) / 100
  estimateResult.value.missing_cost_type_ids = []
}

function copyPrice(value: number) {
  navigator.clipboard.writeText(formatAccounting(value)).then(() => {
    ElMessage.success('已复制')
  })
}

const totalProps = ['total_jita_sell', 'total_jita_buy', 'total_frt_sell', 'total_cost'] as const
const summaryKeyMap: Record<string, keyof EstimateSummary> = {
  total_jita_sell: 'total_jita_sell',
  total_jita_buy: 'total_jita_buy',
  total_frt_sell: 'total_frt_sell',
  total_cost: 'total_cost',
}

function getPercent(row: EstimateItem, prop: string): string {
  if (!estimateResult.value) return ''
  const summaryKey = summaryKeyMap[prop]
  if (!summaryKey) return ''
  const total = estimateResult.value.summary[summaryKey] as number
  const rowVal = (row as Record<string, unknown>)[prop] as number
  if (!total || !rowVal) return ''
  return ((rowVal / total) * 100).toFixed(1) + '%'
}

// ======================= API 调用 =====================
async function handleEstimate() {
  if (!inputText.value.trim()) {
    ElMessage.warning('请粘贴EVE文本内容')
    return
  }

  // 内容未变化且已有结果 UUID → 不重复请求
  if (
    inputText.value === lastEstimatedText &&
    coefficient.value === lastEstimatedCoefficient &&
    route.query.uuid
  ) {
    return
  }

  loading.value = true
  estimateResult.value = null

  try {
    const res = await http.post('/EVE/price-estimator/calculate', {
      text: inputText.value,
      coefficient: coefficient.value,
    })
    const data = await res.json()

    if (data.status !== 200) {
      ElMessage.error(data.message || '估价失败')
      return
    }

    estimateResult.value = data.data

    // 记录本次估算内容，用于后续重复估算判断
    lastEstimatedText = inputText.value
    lastEstimatedCoefficient = coefficient.value

    // 更新 URL 以支持分享
    if (data.data.result_uuid) {
      router.replace({ query: { uuid: data.data.result_uuid } })
    }

    if (data.data.unrecognized_names?.length > 0) {
      ElMessage.warning(
        `以下物品名称未识别: ${data.data.unrecognized_names.join(', ')}`
      )
    }

    if (data.data.missing_cost_type_ids?.length > 0) {
      ElMessage.info(
        `${data.data.missing_cost_type_ids.length} 个物品缺少成本数据，可点击"计算缺失成本"`
      )
    }
  } catch (e) {
    ElMessage.error('估价请求失败，请检查网络或服务器状态')
  } finally {
    loading.value = false
  }
}

async function handleCalculateCost() {
  if (!estimateResult.value?.missing_cost_type_ids?.length) return

  calculatingCost.value = true
  progressVisible.value = true
  progressPercent.value = 0
  progressStep.value = '正在启动计算任务...'
  progressTotal.value = estimateResult.value.missing_cost_type_ids.length
  progressCompleted.value = 0

  try {
    // Step 1: 启动计算任务
    const startRes = await http.post('/EVE/price-estimator/calculate-cost', {
      type_ids: estimateResult.value.missing_cost_type_ids,
      result_uuid: route.query.uuid || undefined,
    })
    const startData = await startRes.json()

    if (startData.status !== 200 || !startData.data?.task_id) {
      ElMessage.error(startData.data?.message || startData.message || '启动计算失败')
      calculatingCost.value = false
      progressVisible.value = false
      return
    }

    const taskId = startData.data.task_id
    progressTotal.value = startData.data.total || progressTotal.value

    if (startData.data.overflow_count > 0) {
      ElMessage.warning(
        `超出单次上限50个，本次计算 ${startData.data.total} 个（跳过 ${startData.data.overflow_count} 个）`
      )
    }

    // Step 2: 轮询进度
    progressTimer = setInterval(async () => {
      try {
        const statusRes = await http.get(
          `/EVE/price-estimator/calculate-cost/status?task_id=${taskId}`
        )
        const statusData = await statusRes.json()

        if (statusData.status !== 200) return

        const prog = statusData.data
        progressStep.value = prog.current_step || '计算中...'
        progressCompleted.value = prog.completed || 0
        progressPercent.value = prog.total > 0
          ? Math.round((prog.completed / prog.total) * 100)
          : 0

        if (prog.status === 'completed') {
          // 计算完成
          clearInterval(progressTimer!)
          progressTimer = null
          progressPercent.value = 100
          progressStep.value = '计算完成，正在更新结果...'

          // 从服务端重新加载完整结果（含前序任务已计算的成本）
          const uuid = route.query.uuid as string | undefined
          if (uuid) {
            try {
              const reloadRes = await http.get(`/EVE/price-estimator/result?uuid=${uuid}`)
              const reloadData = await reloadRes.json()
              if (reloadData.status === 200 && reloadData.data) {
                estimateResult.value = reloadData.data
                // 同步跟踪变量
                lastEstimatedText = reloadData.data.text || lastEstimatedText
                lastEstimatedCoefficient = reloadData.data.coefficient || lastEstimatedCoefficient
              }
            } catch {
              // 重新加载失败，降级为本地更新
              patchCostLocal(prog)
            }
          } else {
            patchCostLocal(prog)
          }

          ElMessage.success(
            `成本计算完成，已合并到系统缓存（共 ${prog.merged_count || '?'} 条）`
          )

          // 延迟关闭进度条
          setTimeout(() => {
            progressVisible.value = false
            calculatingCost.value = false
          }, 1500)
        }

        if (prog.status === 'failed') {
          clearInterval(progressTimer!)
          progressTimer = null
          ElMessage.error(prog.error || '成本计算失败')
          calculatingCost.value = false
          progressVisible.value = false
        }
      } catch {
        // 轮询失败，继续尝试
      }
    }, 2000)
  } catch (e) {
    ElMessage.error('启动成本计算请求失败')
    calculatingCost.value = false
    progressVisible.value = false
  }
}

// ======================= 表格列配置 =====================
const tableColumns = [
  { prop: 'name', label: '物品名', width: 200 },
  { prop: 'quantity', label: '数量', width: 80 },
  { prop: 'jita_sell', label: 'Jita卖(单价)', width: 130 },
  { prop: 'jita_buy', label: 'Jita买(单价)', width: 130 },
  { prop: 'frt_sell', label: '4H卖(单价)', width: 130 },
  { prop: 'cost', label: '成本(单价)', width: 130 },
  { prop: 'total_jita_sell', label: 'Jita卖(总价)', width: 150 },
  { prop: 'total_frt_sell', label: '4H卖(总价)', width: 150 },
  { prop: 'total_cost', label: '成本(总价)', width: 140 },
]

// 表格行高亮 class
function tableRowClassName({ row }: { row: EstimateItem }) {
  if (row.type_id === null) return 'row-unrecognized'
  if (!row.cost_cached && row.has_blueprint) return 'row-missing-cost'
  return ''
}

// 组件卸载时清理轮询定时器
onUnmounted(() => {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
})
</script>

<template>
  <el-container class="estimator-view">
    <el-header class="estimator-header">
      <h1>估价器</h1>
      <p class="header-desc">粘贴EVE游戏文本，快速估算物品价值</p>
    </el-header>

    <el-main class="estimator-main">
      <!-- 结果区域（显示在输入框上方） -->
      <template v-if="estimateResult">
        <!-- 计算进度条 -->
        <el-alert
          v-if="progressVisible"
          type="info"
          :closable="false"
          class="cost-alert"
        >
          <template #title>
            <div class="progress-header">
              <span>正在计算成本...</span>
              <span class="progress-count">
                {{ progressCompleted }} / {{ progressTotal }}
              </span>
            </div>
          </template>
          <div class="progress-body">
            <el-progress
              :percentage="progressPercent"
              :status="progressPercent === 100 ? 'success' : undefined"
              :stroke-width="16"
            />
            <span class="progress-step">{{ progressStep }}</span>
          </div>
        </el-alert>

        <!-- 缺失成本提示 -->
        <el-alert
          v-else-if="showCalculateCostButton"
          type="info"
          :closable="false"
          class="cost-alert"
        >
          <template #title>
            {{ estimateResult!.missing_cost_type_ids.length }} 个可制造物品缺少成本数据
          </template>
          <el-button
            type="warning"
            size="small"
            :disabled="calculatingCost"
            @click="handleCalculateCost"
          >
            计算缺失成本（增量合并到系统缓存）
          </el-button>
        </el-alert>

        <!-- 结果表格 -->
        <el-card class="result-card">
          <el-table
            :data="estimateResult.items"
            :row-class-name="tableRowClassName"
            border
            stripe
            max-height="500"
            style="width: 100%"
          >
            <el-table-column
              v-for="col in tableColumns"
              :key="col.prop"
              :prop="col.prop"
              :label="col.label"
              :width="col.width"
              :sortable="true"
              :align="col.prop === 'name' ? 'left' : 'right'"
            >
              <template #default="{ row }">
                <template v-if="col.prop === 'name'">
                  <div class="item-name">
                    <span>{{ row.name }}</span>
                    <el-tag
                      v-if="row.type_id === null"
                      size="small"
                      type="danger"
                      class="item-tag"
                    >
                      未识别
                    </el-tag>
                    <el-tag
                      v-else-if="!row.has_blueprint"
                      size="small"
                      type="info"
                      class="item-tag"
                    >
                      Jita收单价
                    </el-tag>
                    <el-tag
                      v-else-if="!row.cost_cached"
                      size="small"
                      type="warning"
                      class="item-tag"
                    >
                      缺成本
                    </el-tag>
                  </div>
                </template>
                <template v-else-if="col.prop === 'quantity'">
                  {{ row.quantity.toLocaleString() }}
                </template>
                <template v-else-if="col.prop && col.prop.startsWith('total_')">
                  {{ formatAccounting(row[col.prop as keyof EstimateItem] as number) }}
                  <span class="percent">({{ getPercent(row, col.prop) }})</span>
                </template>
                <template v-else>
                  {{ formatAccounting(row[col.prop as keyof EstimateItem] as number) }}
                </template>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 汇总 -->
        <el-card shadow="hover" class="statistics-card">
          <el-row :gutter="16">
            <el-col :xs="24" :sm="12" :md="6" v-for="card in priceCards" :key="card.label" class="statistic-col">
              <div class="statistic-item" :class="card.accent ? 'accent' : ''" @click="copyPrice(card.value)">
                <el-statistic :value="card.display" suffix=" ISK">
                  <template #title>
                    <span class="statistic-title">{{ card.label }}</span>
                  </template>
                </el-statistic>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </template>

      <!-- 输入区域 -->
      <el-card class="input-card">
        <div class="input-area">
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="12"
            placeholder="在此粘贴EVE文本...
支持以下格式：
• 游戏合同复制（Tab分隔多列）
• 仓库图标/详情/列表复制（Tab分隔）
• 配装文本（[船型名, 配置名] + 物品 x数量）"
            class="text-input"
          />
          <div class="controls-row">
            <div class="coefficient-control">
              <span class="control-label">价格系数</span>
              <el-input-number
                v-model="coefficient"
                :min="0.01"
                :max="10"
                :step="0.05"
                :precision="2"
                size="default"
              />
            </div>
            <el-button
              type="primary"
              :loading="loading"
              :disabled="!inputText.trim()"
              @click="handleEstimate"
            >
              {{ loading ? '估算中...' : '开始估算' }}
            </el-button>
          </div>
        </div>
      </el-card>
    </el-main>
  </el-container>
</template>

<style scoped>
.estimator-view {
  height: 100%;
  padding: 20px;
}

.estimator-header {
  background: var(--k-color-surface);
  border-radius: 12px;
  height: auto;
  padding: 16px 24px;
  border: 1px solid var(--k-color-border);
  margin-bottom: 20px;
}

.estimator-header h1 {
  margin: 0 0 4px 0;
  color: var(--k-color-text);
  font-size: 20px;
}

.header-desc {
  margin: 0;
  font-size: 13px;
  color: var(--k-color-text-secondary);
}

.estimator-main {
  padding: 0;
}

.input-card {
  margin-top: 16px;
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  border-radius: 12px;
  box-shadow: var(--k-shadow-sm);
}

.result-card {
  margin-bottom: 16px;
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  border-radius: 12px;
  box-shadow: var(--k-shadow-sm);
}

.input-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.text-input {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 13px;
}

.controls-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.coefficient-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.control-label {
  color: var(--k-color-text-secondary);
  font-size: 14px;
  white-space: nowrap;
}

.cost-alert {
  margin-bottom: 16px;
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-bottom: 8px;
}

.progress-count {
  font-size: 13px;
  color: var(--k-color-text-secondary);
}

.progress-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.progress-step {
  font-size: 12px;
  color: var(--k-color-text-secondary);
}

.item-name {
  display: flex;
  align-items: center;
  gap: 6px;
}

.item-tag {
  flex-shrink: 0;
}

.percent {
  font-size: 12px;
  color: var(--k-color-text-secondary);
  margin-left: 2px;
}

.statistics-card {
  margin-bottom: 16px;
  border-radius: 12px;
  overflow: hidden;
}

.statistics-card :deep(.el-card__body) {
  padding: 16px 20px;
}

.statistic-col {
  margin-bottom: 12px;
}

.statistic-item {
  padding: 12px 16px;
  border-radius: 10px;
  background: var(--k-color-surface-soft);
  border: 1px solid var(--k-color-border);
  cursor: pointer;
  transition: all 0.2s;
}

.statistic-item:hover {
  border-color: var(--k-color-primary);
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.statistic-item.accent {
  background: color-mix(in srgb, var(--k-color-primary) 6%, var(--k-color-surface));
  border-color: color-mix(in srgb, var(--k-color-primary) 20%, var(--k-color-border));
}

.statistic-title {
  font-size: 13px;
  color: var(--k-color-text-secondary);
  font-weight: 500;
}

/* el-statistic 数字 */
.statistic-item :deep(.el-statistic__number) {
  font-size: 20px;
  font-weight: 700;
  font-family: 'Consolas', 'Courier New', monospace;
}

.statistic-item :deep(.el-statistic__suffix) {
  font-size: 14px;
  font-weight: 600;
}

/* Theme overrides */
.estimator-view,
.estimator-main {
  background: var(--k-color-background) !important;
}

/* 表格行样式 */
:deep(.row-unrecognized) {
  background: color-mix(in srgb, var(--el-color-danger) 6%, transparent) !important;
}

:deep(.row-missing-cost) {
  background: color-mix(in srgb, var(--el-color-warning) 6%, transparent) !important;
}
</style>
