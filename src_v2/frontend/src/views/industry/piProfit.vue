<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { http } from '@/http'
import { VueFlow } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { Background } from '@vue-flow/background'
import { Handle, Position, MarkerType } from '@vue-flow/core'
import dagre from 'dagre'

// ============ TypeScript Interfaces ============

interface PIProduct {
  type_id: number
  name_zh: string
  name_en: string
  tier: number
  output_per_cycle: number
  cycle_time: number
  path_count: number
  best_profit_path: PathProfitData | null
  all_paths: PathProfitData[]
}

interface PathProfitData {
  path_description: string
  tiers: TierInfo[]
  input_items: InputItem[]
  output_item: OutputItem
  input_total_cost: number
  output_total_revenue: number
  profit: number
  profit_margin_pct: number
  tier_details: TierDetail[]
}

interface TierDetail {
  tier: number
  type_id: number
  name_zh: string
  factory_count: number
  inputs: TierInput[]
  tier_input_cost: number
  cumulative_cost: number
  output_qty: number
  output_price: number
  tier_revenue: number
  tier_profit: number
  tier_margin_pct: number
}

interface TierInput {
  type_id: number
  name_zh: string
  quantity: number
  unit_price: number
  total_cost: number
}

interface TierInfo {
  tier: number
  type_id: number
  name_zh: string
  factory_count: number
}

interface InputItem {
  type_id: number
  name_zh: string
  quantity: number
  unit_price: number
  total_cost: number
}

interface OutputItem {
  type_id: number
  name_zh: string
  quantity: number
  unit_price: number
  total_revenue: number
}

// ============ Reactive State ============

const priceBase = ref<'sell' | 'buy' | 'mid'>('sell')
const materialPriceBase = ref<'sell' | 'buy' | 'mid'>('buy')
const tierFilter = ref<number>(0)
const products = ref<PIProduct[]>([])
const loading = ref(false)
const calculating = ref(false)

const tierOptions = [
  { value: 0, label: '全部层级' },
  { value: 4, label: 'P4' },
  { value: 3, label: 'P3' },
  { value: 2, label: 'P2' },
]

const filteredProducts = computed(() => {
  if (tierFilter.value === 0) return products.value
  return products.value.filter(p => p.tier === tierFilter.value)
})

const priceBaseOptions = [
  { value: 'sell', label: '卖出' },
  { value: 'buy', label: '买入' },
  { value: 'mid', label: '中间价' },
]

const cyclesPerMonth = 720

// ============ Product Presets (固定套数配置) ============

/** P2/P3 通用规则：根据产品层级和路径起点确定套数 */
function getDefaultSets(tier: number, path: PathProfitData): number {
  const startTier = parseInt(path.path_description.split('→')[0].replace('P', ''))
  if (tier === 2) return 100                      // P2: P1→P2 = 100套
  if (tier === 3 && startTier === 1) return 20    // P3: P1→P2→P3 = 20套
  if (tier === 3 && startTier === 2) return 100   // P3: P2→P3 = 100套
  return 1
}

/** P4 固定配置：type_id → { sets, defaultPath }
 *  defaultPath: undefined=显示全部路径, 0=仅P1输入, -1=显示全部但标记 */
const P4_PRESETS: Record<number, { sets: number; defaultPath?: number }> = {
  2867: { sets: 5, defaultPath: 0 },   // 广播节点 — 特定输入
  2868: { sets: 5, defaultPath: 0 },   // 反破损快速反应无人机 — 特定输入
  2869: { sets: 5, defaultPath: 0 },   // 纳米工厂 — 仅P1输入
  2870: { sets: 5, defaultPath: 0 },   // 有机砂浆喷注器 — 特定输入
  2871: { sets: 10, defaultPath: 0 },  // 递推计算模块 — 特定输入
  2872: { sets: 5, defaultPath: 0 },   // 自协调能源核心 — 特定输入
  2875: { sets: 10, defaultPath: 0 },  // 无菌管道 — 仅P1输入
  2876: { sets: 10, defaultPath: 0 },  // 湿件主机 — 特定输入
}

function getPathSets(product: PIProduct, path: PathProfitData): number {
  if (product.tier === 4) {
    const preset = P4_PRESETS[product.type_id]
    return preset?.sets ?? 5
  }
  return getDefaultSets(product.tier, path)
}

/** P4 产品根据配置过滤路径：defaultPath 指定时隐藏其他路径 */
function filterPathsForP4(product: PIProduct, paths: PathProfitData[]): PathProfitData[] {
  if (product.tier !== 4) return paths
  const preset = P4_PRESETS[product.type_id]
  if (preset?.defaultPath === undefined) return paths
  return [paths[preset.defaultPath]].filter(Boolean)
}

function pathMonthlyProfit(path: PathProfitData, product: PIProduct): number {
  return path.profit * cyclesPerMonth * getPathSets(product, path)
}

// ============ Dialog State ============

const dialogVisible = ref(false)
const selectedProduct = ref<PIProduct | null>(null)

// ============ Vue Flow State ============

const nodes = ref<any[]>([])
const edges = ref<any[]>([])
const activePathIndex = ref(0)

const currentPath = computed(() => {
  if (!selectedProduct.value || !selectedProduct.value.all_paths.length) return null
  return visiblePaths.value[activePathIndex.value] ?? null
})

/** P4 产品根据配置过滤后可见的路径 */
const visiblePaths = computed(() => {
  if (!selectedProduct.value) return []
  return filterPathsForP4(selectedProduct.value, selectedProduct.value.all_paths)
})

// ============ Vue Flow Graph Builder ============

interface FlowNode {
  id: string
  type: string
  data: Record<string, any>
  style?: Record<string, string>
}

interface FlowEdge {
  id: string
  source: string
  target: string
  type: string
  style: Record<string, string>
  markerEnd: { type: MarkerType }
}

/** Approximate node dimensions for dagre layout */
const NODE_DIMS: Record<string, { w: number; h: number }> = {
  leaf: { w: 140, h: 100 },
  factory: { w: 200, h: 155 },
  output: { w: 200, h: 120 },
}

function buildFlowGraph(path: PathProfitData): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const flowNodes: FlowNode[] = []
  const flowEdges: FlowEdge[] = []
  let leafIdx = 0

  // 按 tier 分组工厂节点
  const tierGroups = new Map<number, number[]>()
  const factoryNodeIds: string[] = []
  const factoryOutputIds = new Set<number>()
  for (let fi = 0; fi < path.tier_details.length; fi++) {
    const td = path.tier_details[fi]
    const fId = `factory-${fi}`
    factoryNodeIds.push(fId)
    factoryOutputIds.add(td.type_id)
    const t = td.tier
    if (!tierGroups.has(t)) tierGroups.set(t, [])
    tierGroups.get(t)!.push(fi)
    flowNodes.push({
      id: fId,
      type: 'pi-node',
      data: { nodeType: 'factory', tierDetail: td },
    })
  }

  // 叶子节点：所有工厂输入中，type_id 不在任何工厂产出里的 → 叶子
  const leafToFactory: number[] = []
  for (let fi = 0; fi < path.tier_details.length; fi++) {
    const td = path.tier_details[fi]
    for (const inp of td.inputs) {
      if (!factoryOutputIds.has(inp.type_id)) {
        flowNodes.push({
          id: `leaf-${leafIdx}`,
          type: 'pi-node',
          data: { nodeType: 'leaf', item: inp },
        })
        leafToFactory.push(fi)
        leafIdx++
      }
    }
  }

  // Output
  flowNodes.push({
    id: 'output',
    type: 'pi-node',
    data: {
      nodeType: 'output',
      outputItem: path.output_item,
      inputTotalCost: path.input_total_cost,
      outputTotalRevenue: path.output_total_revenue,
      profit: path.profit,
    },
  })

  // Edges: leaf → its factory
  for (let li = 0; li < leafIdx; li++) {
    flowEdges.push({
      id: `e-leaf-${li}`,
      source: `leaf-${li}`,
      target: factoryNodeIds[leafToFactory[li]],
      type: 'smoothstep',
      style: { stroke: 'var(--k-color-border)', strokeWidth: '1.5' },
      markerEnd: { type: MarkerType.ArrowClosed },
    })
  }

  // Edges: lower-tier factory → higher-tier factory (matched by type_id)
  // 每个 P2 的产出通过 type_id 匹配到消费它的 P3 的 input type_id
  const sortedTiers = Array.from(tierGroups.keys()).sort((a, b) => a - b)
  for (let ti = 0; ti < sortedTiers.length - 1; ti++) {
    const lowerFactories = tierGroups.get(sortedTiers[ti]) || []
    const higherFactories = tierGroups.get(sortedTiers[ti + 1]) || []
    for (const lf of lowerFactories) {
      const lowerTypeId = path.tier_details[lf].type_id
      for (const hf of higherFactories) {
        const higherInputs = path.tier_details[hf].inputs || []
        if (higherInputs.some((inp: any) => inp.type_id === lowerTypeId)) {
          flowEdges.push({
            id: `e-factory-${lf}-${hf}`,
            source: factoryNodeIds[lf],
            target: factoryNodeIds[hf],
            type: 'smoothstep',
            style: { stroke: 'var(--k-color-border)', strokeWidth: '1.5' },
            markerEnd: { type: MarkerType.ArrowClosed },
          })
        }
      }
    }
  }

  // Edge: highest-tier factory → output
  const highestFactories = tierGroups.get(sortedTiers[sortedTiers.length - 1]) || []
  for (const hf of highestFactories) {
    flowEdges.push({
      id: `e-factory-${hf}-output`,
      source: factoryNodeIds[hf],
      target: 'output',
      type: 'smoothstep',
      style: { stroke: 'var(--k-color-border)', strokeWidth: '1.5' },
      markerEnd: { type: MarkerType.ArrowClosed },
    })
  }

  return { nodes: flowNodes, edges: flowEdges }
}

// ============ Dagre Auto-Layout ============

function getLayoutedElements(rawNodes: FlowNode[], rawEdges: FlowEdge[]) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 50, ranksep: 80 })

  rawNodes.forEach(n => {
    const dim = NODE_DIMS[n.data.nodeType] || { w: 180, h: 120 }
    g.setNode(n.id, { width: dim.w, height: dim.h })
  })

  rawEdges.forEach(e => g.setEdge(e.source, e.target))
  dagre.layout(g)

  return {
    nodes: rawNodes.map(n => {
      const pos = g.node(n.id)
      const dim = NODE_DIMS[n.data.nodeType] || { w: 180, h: 120 }
      return { ...n, position: { x: pos.x - dim.w / 2, y: pos.y - dim.h / 2 } }
    }),
    edges: rawEdges,
  }
}

// ============ Computed: Card Grid Grouping ============

const groupedProducts = computed(() => {
  const groups: Record<number, PIProduct[]> = {}
  for (const p of filteredProducts.value) {
    if (!groups[p.tier]) groups[p.tier] = []
    groups[p.tier].push(p)
  }
  const sorted = Object.entries(groups).sort(([a], [b]) => Number(b) - Number(a))
  return sorted.map(([tier, items]) => ({
    tier: Number(tier),
    label: 'P' + tier,
    items
  }))
})

// ============ Formatting Helpers ============

function formatMoney(n: number): string {
  if (Math.abs(n) >= 1_000_000_000) return (n / 1_000_000_000).toFixed(2) + 'B'
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M'
  return n.toLocaleString()
}
function formatProfitMargin(pct: number): string { return pct.toFixed(1) + '%' }
function marginColorClass(pct: number): string {
  if (pct > 30) return 'margin-high'
  if (pct >= 10) return 'margin-mid'
  return 'margin-low'
}
function tierLabel(tier: number): string { return 'P' + tier }
function tierTagType(tier: number): 'success' | 'warning' | 'danger' | '' {
  if (tier === 4) return 'danger'
  if (tier === 3) return 'warning'
  return 'success'
}
function typeIconUrl(typeId: number, size: number = 64): string {
  return `https://imageserver.eveonline.com/Type/${typeId}_${size}.png`
}

// ============ API Calls ============

async function fetchProducts() {
  loading.value = true
  try {
    const res = await http.get('/EVE/pi/products')
    const data = await res.json()
    if (data.status !== 200) {
      ElMessage.error(data.message || '获取产品列表失败')
      return
    }
    products.value = data.data.products || []
  } catch (error) {
    console.error('获取产品列表失败:', error)
    ElMessage.error('网络请求失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function calculateAll(force = false) {
  calculating.value = true
  try {
      const res = await http.post('/EVE/pi/calculate-all', {
        price_base: priceBase.value,
        material_base: materialPriceBase.value,
        force,
      })
    const data = await res.json()
    if (data.status !== 200) {
      ElMessage.error(data.message || '计算失败')
      return
    }
    products.value = data.data.products || []
    ElMessage.success('计算完成')
  } catch (error) {
    console.error('计算失败:', error)
    ElMessage.error('网络请求失败，请稍后重试')
  } finally {
    calculating.value = false
  }
}

// ============ Dialog Helpers ============

function openPathDetail(product: PIProduct) {
  selectedProduct.value = product
  activePathIndex.value = 0
  dialogVisible.value = true
  buildCurrentGraph()
}

function closeDialog() {
  dialogVisible.value = false
  selectedProduct.value = null
}

/** Rebuild the Vue Flow graph for the currently active path */
function buildCurrentGraph() {
  if (!selectedProduct.value) return
  const path = visiblePaths.value[activePathIndex.value]
  if (!path) return
  const { nodes: rawNodes, edges: rawEdges } = buildFlowGraph(path)
  const layouted = getLayoutedElements(rawNodes, rawEdges)
  nodes.value = layouted.nodes
  edges.value = layouted.edges
}

/** Parse output tier: max tier from factory stages (or input tier + 1) */
function getOutputTier(path: PathProfitData): number {
  if (path.tiers.length > 0) {
    return Math.max(...path.tiers.map(t => t.tier))
  }
  return 1
}

// ============ Watchers ============

watch(activePathIndex, () => {
  if (dialogVisible.value) {
    buildCurrentGraph()
  }
})

function tierBorderColor(tier: number): string {
  if (tier >= 4) return 'var(--k-color-danger)'
  if (tier >= 3) return 'var(--k-color-warning)'
  return 'var(--k-color-success)'
}

function tierBgColor(tier: number): string {
  if (tier >= 4) return 'rgba(239,68,68,0.08)'
  if (tier >= 3) return 'rgba(245,158,11,0.08)'
  return 'rgba(22,163,74,0.08)'
}

// ============ Lifecycle ============

onMounted(() => {
  calculateAll()
})

// 价格基准变化时自动重新计算（3 秒防抖）
let debounceTimer: ReturnType<typeof setTimeout> | null = null
watch([priceBase, materialPriceBase], () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    calculateAll()
  }, 3000)
})

</script>

<template>
  <div class="pi-profit-container">
    <!-- ===== Control Panel ===== -->
    <div class="control-panel">
      <div class="control-row">
        <h2 class="page-title">行星工业利润分析</h2>
        <div class="control-spacer"></div>
        <div class="control-group">
          <span class="control-label">产品价格:</span>
          <el-select v-model="priceBase" size="default" class="control-select">
            <el-option v-for="opt in priceBaseOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </div>
        <div class="control-group">
          <span class="control-label">材料价格:</span>
          <el-select v-model="materialPriceBase" size="default" class="control-select">
            <el-option v-for="opt in priceBaseOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </div>
        <div class="control-group">
          <span class="control-label">层级:</span>
          <el-select v-model="tierFilter" size="default" class="control-select">
            <el-option v-for="opt in tierOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </div>
          <el-button type="primary" :loading="calculating" :disabled="calculating" @click="calculateAll(true)">
            {{ calculating ? '计算中...' : '刷新结果' }}
          </el-button>
          <div class="control-hint">缓存30分钟，点击刷新结果强制重新计算</div>
      </div>
      <div class="control-hint">
        提示: 套数由产品配置固定。P2=100套, P3(P1)=20套, P3(P2)=100套, P4=见配置。点击卡片查看详情。
      </div>
    </div>

    <!-- ===== Card Grid ===== -->
    <div v-loading="loading" class="card-grid-scroll">
      <template v-if="filteredProducts.length === 0 && !loading">
        <div class="empty-state">暂无数据，请点击「刷新结果」加载数据</div>
      </template>
      <template v-else>
        <div v-for="group in groupedProducts" :key="group.tier" class="tier-group">
          <!-- Tier Group Header -->
          <div class="tier-group-header" :style="{ borderLeftColor: tierBorderColor(group.tier) }">
            <img :src="typeIconUrl(group.items[0].type_id)" class="tier-group-icon-img" />
            <span class="tier-group-label">{{ group.label }}</span>
            <span class="tier-group-count">({{ group.items.length }} 产品)</span>
          </div>

          <!-- Card Grid -->
          <div class="card-grid">
            <div
              v-for="product in group.items"
              :key="product.type_id"
              class="product-card"
              :style="{ borderLeftColor: tierBorderColor(group.tier) }"
              @click="openPathDetail(product)"
            >
              <!-- Icon area -->
              <div class="card-icon-area">
                <img :src="typeIconUrl(product.type_id)" class="card-icon-img" />
                <el-tag :type="tierTagType(product.tier)" size="small" effect="dark" class="card-tier-tag">
                  {{ tierLabel(product.tier) }}
                </el-tag>
              </div>

              <!-- Product name -->
              <div class="card-name">{{ product.name_zh }}</div>
              <div class="card-name-en">{{ product.name_en }}</div>

              <div class="card-divider"></div>

              <!-- Per-path profit data -->
              <div class="card-financials">
                <div v-for="p in filterPathsForP4(product, product.all_paths)" :key="p.path_description" class="fin-row">
                  <span class="fin-path-label">{{ p.path_description.split('→')[0] }}输入</span>
                  <span
                    class="fin-value fin-margin"
                    :class="marginColorClass(p.profit_margin_pct)"
                  >{{ formatProfitMargin(p.profit_margin_pct) }}</span>
                  <span class="fin-sep">/</span>
                  <span class="fin-value fin-monthly" :class="p.profit > 0 ? 'profit-positive' : 'profit-negative'">
                    {{ formatMoney(pathMonthlyProfit(p, product)) }}
                  </span>
                </div>
                <div v-if="!product.all_paths.length" class="fin-row">
                  <span class="fin-value fin-na">—</span>
                </div>
              </div>

              <div class="card-divider"></div>

              <!-- Detail action -->
              <div class="card-action">
                <span class="action-text">查看详情 →</span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- ===== Path Tree Dialog ===== -->
    <el-dialog
      v-model="dialogVisible"
      :width="'90%'"
      :top="'2vh'"
      :destroy-on-close="true"
      class="tree-dialog"
      @closed="closeDialog"
    >
      <template #header>
        <div class="dialog-header-custom">
          <span class="dialog-title" v-if="selectedProduct">{{ selectedProduct.name_zh }}</span>
          <el-tag
            v-if="selectedProduct"
            :type="tierTagType(selectedProduct.tier)"
            size="small"
            effect="dark"
            class="dialog-tier-tag"
          >
            {{ tierLabel(selectedProduct.tier) }}
          </el-tag>
        </div>
      </template>

      <div v-if="selectedProduct" class="dialog-body">
        <!-- Path tabs (multiple paths) -->
        <div v-if="visiblePaths.length > 1" class="path-tabs-row">
          <el-radio-group v-model="activePathIndex" size="small">
            <el-radio-button
              v-for="(path, idx) in visiblePaths"
              :key="idx"
              :value="idx"
            >
              {{ path.path_description.split('→')[0] }}输入
            </el-radio-button>
          </el-radio-group>
        </div>

        <!-- Path info bar -->
        <div v-if="currentPath" class="path-info-bar">
          <span class="path-info-desc">{{ currentPath.path_description }}</span>
          <span
            class="path-info-margin"
            :class="marginColorClass(currentPath.profit_margin_pct)"
          >
            利润率: {{ formatProfitMargin(currentPath.profit_margin_pct) }}
          </span>
        </div>

        <!-- Vue Flow diagram -->
        <div class="vue-flow-wrapper">
          <VueFlow
            v-if="nodes.length > 0"
            :key="'flow-' + activePathIndex"
            v-model:nodes="nodes"
            v-model:edges="edges"
            :default-viewport="{ zoom: 1, x: 0, y: 0 }"
            :min-zoom="0.3"
            :max-zoom="2"
            fit-view-on-init
            class="pi-flow"
          >
            <Background :gap="20" />

            <template #node-pi-node="nodeProps">
              <div
                class="pi-flow-node"
                :class="'pi-fn-' + nodeProps.data.nodeType"
                :style="nodeProps.data.nodeType === 'factory' ? { borderLeftColor: tierBorderColor(nodeProps.data.tierDetail.tier) } : {}"
              >
                <Handle
                  v-if="nodeProps.data.nodeType !== 'leaf'"
                  type="target"
                  :position="Position.Top"
                />

                <!-- Leaf: P1 input -->
                <template v-if="nodeProps.data.nodeType === 'leaf'">
                  <img :src="typeIconUrl(nodeProps.data.item.type_id)" class="pi-fn-icon" />
                  <div class="pi-fn-name">{{ nodeProps.data.item.name_zh }}</div>
                  <div class="pi-fn-qty">×{{ nodeProps.data.item.quantity }}</div>
                  <div class="pi-fn-price">{{ formatMoney(nodeProps.data.item.unit_price) }}</div>
                </template>

                <!-- Factory node -->
                <template v-if="nodeProps.data.nodeType === 'factory'">
                  <img :src="typeIconUrl(nodeProps.data.tierDetail.type_id)" class="pi-fn-icon" />
                  <div class="pi-fn-name">{{ nodeProps.data.tierDetail.name_zh }}</div>
                  <div class="pi-fn-tier">P{{ nodeProps.data.tierDetail.tier }}</div>
                  <div class="pi-fn-divider"></div>
                  <div class="pi-fn-detail">投入 {{ formatMoney(nodeProps.data.tierDetail.tier_input_cost) }}</div>
                  <div class="pi-fn-detail">产出 ×{{ nodeProps.data.tierDetail.output_qty }} {{ formatMoney(nodeProps.data.tierDetail.output_price) }}/个</div>
                  <div class="pi-fn-profit" :class="marginColorClass(nodeProps.data.tierDetail.tier_margin_pct)">
                    {{ formatMoney(nodeProps.data.tierDetail.tier_profit) }} ({{ formatProfitMargin(nodeProps.data.tierDetail.tier_margin_pct) }})
                  </div>
                </template>

                <!-- Output node -->
                <template v-if="nodeProps.data.nodeType === 'output'">
                  <img :src="typeIconUrl(nodeProps.data.outputItem.type_id)" class="pi-fn-icon" />
                  <div class="pi-fn-name">{{ nodeProps.data.outputItem.name_zh }}</div>
                  <div class="pi-fn-tier">产出</div>
                  <div class="pi-fn-divider"></div>
                  <div class="pi-fn-detail">×{{ nodeProps.data.outputItem.quantity }} {{ formatMoney(nodeProps.data.outputItem.unit_price) }}/个</div>
                  <div class="pi-fn-detail">合计 {{ formatMoney(nodeProps.data.outputItem.total_revenue) }}</div>
                </template>

                <Handle
                  v-if="nodeProps.data.nodeType !== 'output'"
                  type="source"
                  :position="Position.Bottom"
                />
              </div>
            </template>
          </VueFlow>
        </div>

        <!-- Total bar -->
        <div v-if="currentPath" class="flow-total-bar">
          <span>总投入: <strong>{{ formatMoney(currentPath.input_total_cost) }}</strong></span>
          <span class="total-sep">|</span>
          <span>总利润率: <strong :class="marginColorClass(currentPath.profit_margin_pct)">{{ formatProfitMargin(currentPath.profit_margin_pct) }}</strong></span>
          <span class="total-sep">|</span>
          <span>总利润: <strong :class="currentPath.profit > 0 ? 'profit-positive' : 'profit-negative'">{{ formatMoney(currentPath.profit) }}</strong></span>
          <span class="total-sep">|</span>
          <span>月利润: <strong class="profit-positive">{{ formatMoney(pathMonthlyProfit(currentPath, selectedProduct!)) }}</strong> ({{ getPathSets(selectedProduct!, currentPath) }}套, 720轮)</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ================================================================
   CONTAINER
   ================================================================ */
.pi-profit-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ================================================================
   CONTROL PANEL
   ================================================================ */
.control-panel {
  flex-shrink: 0;
  padding: 16px 20px;
  margin-bottom: 12px;
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  border-radius: var(--k-radius-md);
  box-shadow: var(--k-shadow-sm);
}

.control-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
  color: var(--k-color-text);
  white-space: nowrap;
}

.control-spacer {
  flex: 1;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.control-label {
  font-size: 13px;
  color: var(--k-color-text-secondary);
  white-space: nowrap;
}

.control-unit {
  font-size: 13px;
  color: var(--k-color-text-secondary);
}

.control-input-number {
  width: 115px;
}

.control-select {
  width: 105px;
}

.control-hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--k-color-text-secondary);
}

/* ================================================================
   CARD GRID SCROLL CONTAINER
   ================================================================ */
.card-grid-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
}

.empty-state {
  text-align: center;
  padding: 64px 20px;
  color: var(--k-color-text-secondary);
  font-size: 15px;
}

/* ================================================================
   TIER GROUP
   ================================================================ */
.tier-group {
  margin-bottom: 24px;
}

.tier-group:last-child {
  margin-bottom: 8px;
}

.tier-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  border-left: 4px solid;
  border-radius: 0 var(--k-radius-sm) var(--k-radius-sm) 0;
  box-shadow: var(--k-shadow-sm);
}

.tier-group-icon-img {
  width: 32px;
  height: 32px;
  object-fit: contain;
}

.tier-group-label {
  font-size: 16px;
  font-weight: 700;
  color: var(--k-color-text);
}

.tier-group-count {
  font-size: 13px;
  color: var(--k-color-text-secondary);
}

/* ================================================================
   CARD GRID
   ================================================================ */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}

/* ================================================================
   PRODUCT CARD
   ================================================================ */
.product-card {
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  border-left: 4px solid;
  border-radius: var(--k-radius-sm);
  box-shadow: var(--k-shadow-sm);
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
}

.product-card:hover {
  box-shadow: 0 4px 20px rgba(0,0,0,0.12);
  transform: translateY(-2px);
  border-color: var(--k-color-primary);
}

/* Icon area */
.card-icon-area {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.card-icon-img {
  width: 48px;
  height: 48px;
  object-fit: contain;
}

.card-tier-tag {
  flex-shrink: 0;
}

/* Names */
.card-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--k-color-text);
  line-height: 1.3;
  margin-bottom: 2px;
}

.card-name-en {
  font-size: 12px;
  color: var(--k-color-text-secondary);
  margin-bottom: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-divider {
  height: 1px;
  background: var(--k-color-border);
  margin: 8px 0;
}

/* Per-path profit rows */
.card-financials {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.fin-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.fin-path-label {
  color: var(--k-color-text-secondary);
  font-size: 11px;
  min-width: 48px;
}

.fin-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--k-color-text);
}

.fin-margin {
  padding: 0 4px;
  border-radius: 3px;
}

.fin-sep {
  color: var(--k-color-border);
  margin: 0 2px;
}

.fin-monthly {
  font-size: 13px;
}

.fin-na {
  color: var(--k-color-text-secondary);
  font-weight: 400;
}

/* Action */
.card-action {
  margin-top: 6px;
  display: flex;
  justify-content: flex-end;
}

.action-text {
  font-size: 13px;
  color: var(--k-color-primary);
  font-weight: 500;
  transition: transform 0.15s ease;
}

.product-card:hover .action-text {
  transform: translateX(3px);
}

/* ================================================================
   MARGIN COLOR CLASSES
   ================================================================ */
.margin-high {
  color: #16a34a;
  background: rgba(22, 163, 74, 0.1);
}

.margin-mid {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.1);
}

.margin-low {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.profit-positive {
  color: #16a34a;
}

.profit-negative {
  color: #ef4444;
}

/* ================================================================
   DIALOG
   ================================================================ */
.tree-dialog :deep(.el-dialog__header) {
  padding: 16px 24px 12px;
  border-bottom: 1px solid var(--k-color-border);
}

.tree-dialog :deep(.el-dialog__body) {
  padding: 16px 24px;
  max-height: calc(96vh - 100px);
  overflow-y: auto;
}

.dialog-header-custom {
  display: flex;
  align-items: center;
  gap: 10px;
}

.dialog-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--k-color-text);
}

.dialog-tier-tag {
  flex-shrink: 0;
}

.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* ================================================================
   PATH SECTION
   ================================================================ */
.path-section + .path-section {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 2px dashed var(--k-color-border);
}

/* Multi-path divider */
.path-divider {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 18px;
  padding: 10px 16px;
  background: var(--k-color-surface-soft);
  border-radius: var(--k-radius-sm);
  flex-wrap: wrap;
}

.path-divider-label {
  font-size: 15px;
  font-weight: 700;
  color: var(--k-color-text);
}

.path-divider-margin {
  font-size: 13px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

/* Single path header */
.path-single-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}

.path-single-label {
  font-size: 15px;
  font-weight: 700;
  color: var(--k-color-text);
}

.path-single-margin {
  font-size: 13px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

/* ================================================================
   TREE ROOT
   ================================================================ */
.tree-root {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  width: 100%;
}

/* ================================================================
   TREE LEVEL (one horizontal row of nodes)
   ================================================================ */
.tree-level {
  width: 100%;
}

.tree-level-label {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 16px;
  font-size: 13px;
  color: var(--k-color-text-secondary);
}

.level-badge {
  color: #fff;
  padding: 1px 8px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: 700;
}

.tree-level-row {
  display: flex;
  justify-content: center;
  align-items: flex-end;
  gap: 12px;
  padding: 8px 20px;
}

.tree-level-center {
  justify-content: center;
}

.tree-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
}

.tree-col-sep {
  width: 24px;
  flex-shrink: 0;
}

.tree-col-cards {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

/* ================================================================
   TREE NODES (cards at each level)
   ================================================================ */
.tree-node {
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  border-radius: 6px;
  padding: 10px 12px;
  min-width: 100px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.tree-node-icon {
  width: 36px;
  height: 36px;
  object-fit: contain;
}

.tree-node-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--k-color-text);
  text-align: center;
}

.tree-node-qty {
  font-size: 12px;
  color: var(--k-color-primary);
}

.tree-node-price {
  font-size: 12px;
  color: var(--k-color-text-secondary);
}

.tree-node-tier {
  font-size: 11px;
  color: var(--k-color-text-secondary);
  font-weight: 600;
}

.tree-node-divider {
  width: 100%;
  height: 1px;
  background: var(--k-color-border);
  margin: 2px 0;
  opacity: 0.5;
}

.tree-node-detail {
  font-size: 12px;
  color: var(--k-color-text-secondary);
  text-align: center;
}

.tree-node-profit {
  font-size: 13px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
  margin-top: 2px;
}

.leaf-node {
  background: color-mix(in srgb, var(--k-color-surface-soft) 80%, transparent);
}

.factory-node {
  border-left: 4px solid var(--k-color-warning);
  min-width: 180px;
}

.output-node {
  border-left: 4px solid var(--k-color-primary);
  min-width: 200px;
}

/* ================================================================
   TREE CONNECTORS (vertical stems)
   ================================================================ */
.tree-connector-v {
  display: flex;
  justify-content: center;
  width: 100%;
}

.tree-connector-line {
  width: 2px;
  height: 20px;
  background: var(--k-color-border);
  opacity: 0.7;
}

/* ================================================================
   TREE BRIDGE (horizontal merge connectors)
   ================================================================ */
.tree-bridge {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 0 30px;
  width: 100%;
}

.tree-bridge-stem {
  width: 2px;
  height: 16px;
  background: var(--k-color-border);
  opacity: 0.7;
}

.center-stem {
  margin: 0 auto;
}

/* Merge bridge: multiple columns → single center */
.tree-bridge-merge {
  position: relative;
  padding: 0 60px;
}

.tree-bridge-merge-bar {
  width: 100%;
  height: 2px;
  background: var(--k-color-border);
  opacity: 0.7;
  position: relative;
}

/* ================================================================
   TREE BRIDGE (horizontal merge connectors)
   ================================================================ */
.tree-bridge {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 0 30px;
  width: 100%;
}

.tree-bridge-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  max-width: 200px;
}

.tree-bridge-stem {
  width: 2px;
  height: 20px;
  background: var(--k-color-border);
}

.center-stem {
  margin: 0 auto;
}

/* Merge bridge: multiple columns → single center */
.tree-bridge-merge {
  position: relative;
  padding: 0 60px;
}

.tree-bridge-merge-bar {
  width: 100%;
  height: 2px;
  background: var(--k-color-border);
  position: relative;
  top: 0;
}

.tree-bridge-merge .tree-bridge-stem {
  position: relative;
  top: -2px;
}

/* ================================================================
   TREE LEVEL SUMMARY
   ================================================================ */
.tree-level-summary {
  text-align: center;
  padding: 8px 0;
  font-size: 14px;
  color: var(--k-color-text-secondary);
  border-top: 1px dashed var(--k-color-border);
  margin: 0 30px;
}

.tree-level-summary strong {
  color: var(--k-color-text);
}

/* ================================================================
   TREE TOTAL BAR
   ================================================================ */
.tree-total-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 24px;
  background: var(--k-color-surface-soft);
  border: 1px solid var(--k-color-border);
  border-radius: 6px;
  font-size: 14px;
  color: var(--k-color-text-secondary);
  flex-wrap: wrap;
  justify-content: center;
}

.tree-total-bar strong {
  color: var(--k-color-text);
}

.tree-total-sep {
  color: var(--k-color-border);
}

/* ================================================================
   DEEP OVERRIDES
   ================================================================ */
:deep(.el-input-number .el-input__wrapper),
:deep(.el-select .el-select__wrapper) {
  background: var(--k-color-surface);
  border-color: var(--k-color-border);
  color: var(--k-color-text);
}

:deep(.el-loading-mask) {
  background-color: color-mix(in srgb, var(--k-color-surface) 70%, transparent);
  border-radius: var(--k-radius-sm);
}

/* ================================================================
   RESPONSIVE
   ================================================================ */
@media (max-width: 768px) {
  .control-row {
    flex-direction: column;
    align-items: flex-start;
  }
  .control-spacer { display: none; }
  .control-input-number { width: 100px; }
  .control-select { width: 95px; }
  .card-grid { grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; }
  .tree-level-row { flex-direction: column; align-items: center; }
  .tree-bridge { flex-direction: column; align-items: center; }
  .tree-col-sep { display: none; }
}

/* ================================================================
   PATH TABS & INFO BAR (Vue Flow Dialog)
   ================================================================ */
.path-tabs-row {
  margin-bottom: 14px;
}

.path-info-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 10px;
  padding: 8px 14px;
  background: var(--k-color-surface-soft);
  border-radius: var(--k-radius-sm);
  flex-wrap: wrap;
}

.path-info-desc {
  font-size: 14px;
  font-weight: 700;
  color: var(--k-color-text);
}

.path-info-margin {
  font-size: 13px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

/* ================================================================
   VUE FLOW WRAPPER
   ================================================================ */
.vue-flow-wrapper {
  height: calc(96vh - 220px);
  min-height: 400px;
  width: 100%;
  overflow: hidden;
  border: 1px solid var(--k-color-border);
  border-radius: var(--k-radius-sm);
  background: var(--k-color-surface);
  margin-bottom: 14px;
}

:deep(.pi-flow) {
  background: var(--k-color-surface);
}

:deep(.vue-flow__background pattern circle) {
  fill: var(--k-color-border);
  opacity: 0.3;
}

:deep(.vue-flow__edge-path) {
  stroke: var(--k-color-border);
}

/* ================================================================
   CUSTOM PI FLOW NODE
   ================================================================ */
.pi-flow-node {
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  border-left: 3px solid transparent;
  border-radius: 8px;
  padding: 10px 12px;
  min-width: 110px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  font-size: 12px;
  color: var(--k-color-text);
}

.pi-fn-leaf {
  background: color-mix(in srgb, var(--k-color-surface-soft) 80%, transparent);
}

.pi-fn-factory {
  border-left: 3px solid var(--k-color-warning);
  min-width: 180px;
}

.pi-fn-output {
  border-left: 3px solid var(--k-color-primary);
  min-width: 190px;
}

.pi-fn-icon {
  width: 36px;
  height: 36px;
  object-fit: contain;
}

.pi-fn-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--k-color-text);
  text-align: center;
  line-height: 1.3;
}

.pi-fn-qty {
  font-size: 12px;
  color: var(--k-color-primary);
}

.pi-fn-price {
  font-size: 12px;
  color: var(--k-color-text-secondary);
}

.pi-fn-tier {
  font-size: 11px;
  color: var(--k-color-text-secondary);
  font-weight: 600;
}

.pi-fn-divider {
  width: 100%;
  height: 1px;
  background: var(--k-color-border);
  margin: 3px 0;
  opacity: 0.5;
}

.pi-fn-detail {
  font-size: 11px;
  color: var(--k-color-text-secondary);
  text-align: center;
  line-height: 1.4;
}

.pi-fn-profit {
  font-size: 12px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  margin-top: 2px;
  white-space: nowrap;
}

/* Hide default handles, show on hover */
:deep(.vue-flow__handle) {
  opacity: 0;
}

:deep(.vue-flow__handle:hover) {
  opacity: 1;
}

/* ================================================================
   FLOW TOTAL BAR
   ================================================================ */
.flow-total-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 24px;
  background: var(--k-color-surface-soft);
  border: 1px solid var(--k-color-border);
  border-radius: 6px;
  font-size: 14px;
  color: var(--k-color-text-secondary);
  flex-wrap: wrap;
  justify-content: center;
}

.flow-total-bar strong {
  color: var(--k-color-text);
}

.total-sep {
  color: var(--k-color-border);
}
</style>
