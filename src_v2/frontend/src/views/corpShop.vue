<script setup lang="ts">
import KTable from '@/components/k/KTable.vue'
import KEmpty from '@/components/k/KEmpty.vue'
import KCard from '@/components/k/KCard.vue'
import { ref, computed, onMounted } from 'vue'
import { http } from '@/http'
import { ElMessage } from 'element-plus'

// ======================= Types =====================
interface DetailItem {
  offer_id: number
  type_id: number
  type_name_en: string
  type_name_zh: string
  quantity: number
  lp_cost: number
  isk_cost: number
  market_buy_price: number
  market_sell_price: number
  daily_volume_30d: number
  daily_value_30d: number
  lp_buy_value: number
  lp_sell_value: number
  is_in_top: boolean
  excluded: boolean
  excluded_reason: string | null
}

interface CorpRow {
  corporation_id: number
  corporation_name: string
  corporation_name_zh: string
  faction_id: number
  lp_buy_value: number
  lp_sell_value: number
  lp_sell_value_all: number
  total_offers: number
  evaluated_offers: number
  excluded_offers: number
}

interface SnapshotData {
  snapshot_date: string
  data: CorpRow[]
}

// ======================= State =====================
const loading = ref(false)
const snapshotDate = ref('')
const rawData = ref<CorpRow[]>([])

// Dialog
const dialogVisible = ref(false)
const dialogLoading = ref(false)
const dialogCorpName = ref('')
const dialogItems = ref<DetailItem[]>([])

// ======================= Computed ===================
const corpList = computed<CorpRow[]>(() => {
  return [...rawData.value].sort((a, b) => b.lp_sell_value - a.lp_sell_value)
})

const evaluatedItems = computed(() => dialogItems.value.filter(i => !i.excluded))
const excludedItems = computed(() => dialogItems.value.filter(i => i.excluded))

// ======================= Formatting ===================
function formatIsk(value: number): string {
  if (value >= 1_000_000_000) return (value / 1_000_000_000).toFixed(2) + 'B'
  if (value >= 1_000_000) return (value / 1_000_000).toFixed(2) + 'M'
  if (value >= 1_000) return (value / 1_000).toFixed(2) + 'K'
  return value.toFixed(2)
}

function formatLp(value: number): string {
  return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatNumber(value: number): string {
  return value.toLocaleString()
}

const excludeReasonMap: Record<string, string> = {
  has_required_items: '需要兑换材料',
  has_ak_cost: '需要分析信用点',
  is_bpc: '蓝图拷贝',
  no_buy_price: '无市场买单价',
  low_daily_value: '日均成交额不足',
  is_bpc_no_product: '蓝图无制造产品',
  is_bpc_no_product_price: '成品无市场卖价',
  anomalous_lp_value: 'LP单价异常（>10k）',
}

// ======================= Data Fetching ===================
async function fetchData() {
  loading.value = true
  try {
    const response = await http.get('/EVE/lp/snapshot/latest')
    const data = await response.json() as { status: number; data?: SnapshotData; message?: string }

    if (data.status !== 200 || !data.data) {
      ElMessage.error(data.message || '获取 LP 快照数据失败')
      return
    }

    snapshotDate.value = data.data.snapshot_date
    rawData.value = data.data.data || []
  } catch (e) {
    ElMessage.error('获取 LP 快照数据失败：网络错误')
  } finally {
    loading.value = false
  }
}

async function openCorpDetail(row: CorpRow) {
  dialogCorpName.value = row.corporation_name_zh || row.corporation_name
  dialogVisible.value = true
  dialogLoading.value = true
  dialogItems.value = []
  try {
    const response = await http.get(`/EVE/lp/snapshot/latest/corp/${row.corporation_id}`)
    const data = await response.json() as { status: number; data: DetailItem[] }
    if (data.status === 200) {
      dialogItems.value = data.data || []
    }
  } catch (e) {
    ElMessage.error('获取军团详情失败')
  } finally {
    dialogLoading.value = false
  }
}

// ======================= Lifecycle ===================
onMounted(() => {
  fetchData()
})
</script>

<template>
  <div class="lp-store-page">
    <!-- Header -->
    <div class="page-header">
      <div class="header-content">
        <div class="header-title-row">
          <span class="header-accent" aria-hidden="true" />
          <h1>LP 商店价值评估</h1>
        </div>
        <p v-if="snapshotDate" class="header-subtitle">快照日期：{{ snapshotDate }}</p>
      </div>
      <div class="header-glow" />
    </div>

    <!-- Empty State -->
    <KEmpty why="暂无 LP 快照数据" v-if="!loading && corpList.length === 0" size="lg" />

    <!-- Table -->
    <KCard v-else class="table-card">
      <KTable
        v-loading="loading"
        :data="corpList"
        row-key="corporation_id"
        stripe
        style="width: 100%"
        :default-sort="{ prop: 'lp_sell_value', order: 'descending' }"
        max-height="calc(100vh - 200px)"
        @row-click="openCorpDetail"
      >
        <!-- Rank -->
        <el-table-column label="排名" type="index" width="70" align="center" />

        <!-- Corporation Name：用 min-width 让这一列吸收多余宽度，表格才不会右侧留一大片空白 -->
        <el-table-column label="军团名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="corp-name-cell" style="cursor: pointer">
              <span class="corp-name-zh">{{ row.corporation_name_zh || row.corporation_name }}</span>
              <span v-if="row.corporation_name_zh" class="corp-name-en">{{ row.corporation_name }}</span>
            </div>
          </template>
        </el-table-column>

        <!-- Faction ID -->
        <el-table-column label="势力ID" prop="faction_id" width="90" align="center" />

        <!-- LP Buy Value -->
        <el-table-column label="LP收单价值" width="130" align="right" sortable prop="lp_buy_value">
          <template #default="{ row }">
            <span class="lp-buy-value">{{ formatLp(row.lp_buy_value) }}</span>
          </template>
        </el-table-column>

        <!-- LP Sell Value -->
        <el-table-column label="LP出单价值" width="130" align="right" sortable prop="lp_sell_value">
          <template #default="{ row }">
            <span class="lp-sell-value">{{ formatLp(row.lp_sell_value) }}</span>
          </template>
        </el-table-column>

        <!-- LP Sell Value All -->
        <el-table-column label="LP出单(全)" width="130" align="right" sortable prop="lp_sell_value_all">
          <template #default="{ row }">
            <span class="lp-sell-value">{{ formatLp(row.lp_sell_value_all) }}</span>
          </template>
        </el-table-column>

        <!-- Evaluated Offers -->
        <el-table-column label="有效/总数" width="110" align="center">
          <template #default="{ row }">
            <span class="offer-count">{{ row.evaluated_offers }} / {{ row.total_offers }}</span>
          </template>
        </el-table-column>
      </KTable>
    </KCard>

    <!-- Detail Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="`${dialogCorpName} — LP 兑换详情`"
      width="90%"
      top="3vh"
      destroy-on-close
    >
      <KTable
        v-loading="dialogLoading"
        :data="evaluatedItems"
        size="small"
        stripe
        style="width: 100%"
        :default-sort="{ prop: 'lp_sell_value', order: 'descending' }"
        max-height="65vh"
      >
        <el-table-column label="物品名" min-width="160" sortable prop="type_name_zh">
          <template #default="{ row }">
            <span>{{ row.type_name_zh || row.type_name_en }}</span>
          </template>
        </el-table-column>
        <el-table-column label="TypeID" prop="type_id" width="80" align="center" />
        <el-table-column label="数量" prop="quantity" width="70" align="center" />
        <el-table-column label="LP消耗" prop="lp_cost" width="100" align="right" sortable>
          <template #default="{ row }">{{ formatNumber(row.lp_cost) }}</template>
        </el-table-column>
        <el-table-column label="ISK消耗" width="110" align="right" sortable prop="isk_cost">
          <template #default="{ row }">{{ formatIsk(row.isk_cost) }}</template>
        </el-table-column>
        <el-table-column label="收单价" width="120" align="right" sortable prop="market_buy_price">
          <template #default="{ row }">{{ formatIsk(row.market_buy_price) }}</template>
        </el-table-column>
        <el-table-column label="出单价" width="120" align="right" sortable prop="market_sell_price">
          <template #default="{ row }">{{ formatIsk(row.market_sell_price) }}</template>
        </el-table-column>
        <el-table-column label="日均成交额" width="140" align="right" sortable prop="daily_value_30d">
          <template #default="{ row }">{{ formatIsk(row.daily_value_30d) }}</template>
        </el-table-column>
        <el-table-column label="LP收单" width="110" align="right" sortable prop="lp_buy_value">
          <template #default="{ row }">
            <span :class="{ 'is-top': row.is_in_top }" class="lp-buy-value">{{ formatLp(row.lp_buy_value) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="LP出单" width="110" align="right" sortable prop="lp_sell_value">
          <template #default="{ row }">
            <span :class="{ 'is-top': row.is_in_top }" class="lp-sell-value">{{ formatLp(row.lp_sell_value) }}</span>
          </template>
        </el-table-column>
      </KTable>

      <!-- Excluded items -->
      <el-divider v-if="excludedItems.length" />
      <el-collapse v-if="excludedItems.length">
        <el-collapse-item :title="`已排除物品 (${excludedItems.length})`">
          <KTable :data="excludedItems" size="small" style="width: 100%" max-height="300">
            <el-table-column label="物品名" min-width="160">
              <template #default="{ row }">{{ row.type_name_zh || row.type_name_en }}</template>
            </el-table-column>
            <el-table-column label="TypeID" prop="type_id" width="80" align="center" />
            <el-table-column label="排除原因" min-width="160">
              <template #default="{ row }">
                <el-tag size="small" type="info">
                  {{ excludeReasonMap[row.excluded_reason] || row.excluded_reason }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="LP消耗" prop="lp_cost" width="100" align="right" />
          </KTable>
        </el-collapse-item>
      </el-collapse>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ======================= Page Layout =================== */
.lp-store-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ======================= Header =================== */
.page-header {
  position: relative;
  padding: 20px 24px 16px;
  flex-shrink: 0;
}

.header-content {
  position: relative;
  z-index: 1;
}

/* 标题行：竖条与标题垂直居中，不再让竖条单独占一行 */
.header-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-title-row h1 {
  margin: 0;
  font-size: 24px;
  line-height: 1.3;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--k-color-text);
}

.header-accent {
  flex: 0 0 4px;
  width: 4px;
  height: 24px;
  border-radius: 2px;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--k-color-primary) 90%, var(--k-color-tint)) 0%,
    var(--k-color-primary) 100%
  );
  box-shadow: 0 0 10px color-mix(in srgb, var(--k-color-primary) 45%, transparent);
}

.page-header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.04em;
  background: linear-gradient(
    135deg,
    var(--k-color-text) 0%,
    color-mix(in srgb, var(--k-color-primary) 65%, var(--k-color-text)) 100%
  );
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.header-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--k-color-text-secondary);
}

.header-glow {
  position: absolute;
  top: -40%;
  right: -2%;
  width: 180px;
  height: 180px;
  border-radius: 50%;
  background: radial-gradient(
    circle,
    color-mix(in srgb, var(--k-color-primary) 18%, transparent) 0%,
    transparent 70%
  );
  pointer-events: none;
  opacity: 0.7;
}

/* ======================= Table Card =================== */
.table-card {
  flex: 1;
  margin: 0 24px 24px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.table-card :deep(.k-card__body) {
  flex: 1;
  overflow: auto;
  padding: 0;
}

/* ======================= Corporation Name Cell =================== */
.corp-name-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.corp-name-zh {
  font-weight: 500;
  color: var(--k-color-text);
}

.corp-name-en {
  font-size: 12px;
  color: var(--k-color-text-secondary);
}

/* ======================= LP Sell Value =================== */
.lp-sell-value,
.lp-buy-value {
  font-weight: 600;
  color: var(--k-color-primary);
}

/* ======================= Offer Count =================== */
.offer-count {
  font-size: 13px;
  color: var(--k-color-text-secondary);
}

/* ======================= Corp Row =================== */
.corp-row {
  cursor: pointer;
}

/* ======================= Top-5 Highlight =================== */
.is-top {
  color: var(--el-color-warning);
  font-weight: 700;
}
</style>
