<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { VueFlow } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { Background } from '@vue-flow/background'
import { Handle, Position, MarkerType } from '@vue-flow/core'
import { http } from '@/http'
import dagre from 'dagre'

// ============ Types ============
interface PathProfitData {
  path_description: string
  tiers: { tier: number; type_id: number; name_zh: string; factory_count: number }[]
  input_items: { type_id: number; name_zh: string; quantity: number; unit_price: number; total_cost: number }[]
  output_item: { type_id: number; name_zh: string; quantity: number; unit_price: number; total_revenue: number }
  input_total_cost: number
  output_total_revenue: number
  profit: number
  profit_margin_pct: number
  tier_details: TierDetail[]
}

interface TierDetail {
  tier: number; type_id: number; name_zh: string; factory_count: number
  inputs: { type_id: number; name_zh: string; quantity: number; unit_price: number; total_cost: number }[]
  tier_input_cost: number; cumulative_cost: number
  output_qty: number; output_price: number
  tier_revenue: number; tier_profit: number; tier_margin_pct: number
}

// ============ State ============
const typeId = ref(0)
const loading = ref(true)
const product = ref<any>(null)
const currentPath = ref<PathProfitData | null>(null)
const activePathIndex = ref(0)

const nodes = ref<any[]>([])
const edges = ref<any[]>([])

const visiblePaths = computed(() => {
  if (!product.value) return []
  const paths = product.value.all_paths || []
  return paths.slice(0, 1) // defaultPath: 0
})

// ============ Formatting ============
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
function typeIconUrl(typeId: number): string {
  return `https://imageserver.eveonline.com/Type/${typeId}_64.png`
}
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

// ============ Graph Builder ============
const NODE_DIMS: Record<string, { w: number; h: number }> = {
  leaf: { w: 140, h: 100 },
  factory: { w: 220, h: 170 },
  output: { w: 220, h: 120 },
}

function buildFlowGraph(path: PathProfitData) {
  const flowNodes: any[] = [], flowEdges: any[] = []
  let leafIdx = 0
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
    flowNodes.push({ id: fId, type: 'pi-node', data: { nodeType: 'factory', tierDetail: td } })
  }

  const leafToFactory: number[] = []
  for (let fi = 0; fi < path.tier_details.length; fi++) {
    const td = path.tier_details[fi]
    for (const inp of td.inputs) {
      if (!factoryOutputIds.has(inp.type_id)) {
        flowNodes.push({ id: `leaf-${leafIdx}`, type: 'pi-node', data: { nodeType: 'leaf', item: inp } })
        leafToFactory.push(fi)
        leafIdx++
      }
    }
  }

  flowNodes.push({ id: 'output', type: 'pi-node', data: { nodeType: 'output', outputItem: path.output_item } })

  for (let li = 0; li < leafIdx; li++) {
    flowEdges.push({ id: `e-leaf-${li}`, source: `leaf-${li}`, target: factoryNodeIds[leafToFactory[li]], type: 'smoothstep', style: { stroke: '#888', strokeWidth: '1.5' }, markerEnd: { type: MarkerType.ArrowClosed } })
  }

  const sortedTiers = Array.from(tierGroups.keys()).sort((a, b) => a - b)
  for (let ti = 0; ti < sortedTiers.length - 1; ti++) {
    for (const lf of (tierGroups.get(sortedTiers[ti]) || [])) {
      for (const hf of (tierGroups.get(sortedTiers[ti + 1]) || [])) {
        if ((path.tier_details[hf].inputs || []).some((inp: any) => inp.type_id === path.tier_details[lf].type_id)) {
          flowEdges.push({ id: `e-f-${lf}-${hf}`, source: factoryNodeIds[lf], target: factoryNodeIds[hf], type: 'smoothstep', style: { stroke: '#888', strokeWidth: '1.5' }, markerEnd: { type: MarkerType.ArrowClosed } })
        }
      }
    }
  }

  const highest = tierGroups.get(sortedTiers[sortedTiers.length - 1]) || []
  for (const hf of highest) {
    flowEdges.push({ id: `e-f-${hf}-out`, source: factoryNodeIds[hf], target: 'output', type: 'smoothstep', style: { stroke: '#888', strokeWidth: '1.5' }, markerEnd: { type: MarkerType.ArrowClosed } })
  }

  return { nodes: flowNodes, edges: flowEdges }
}

function getLayoutedElements(rawNodes: any[], rawEdges: any[]) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 50, ranksep: 80 })
  for (const n of rawNodes) {
    const dim = NODE_DIMS[n.data.nodeType] || { w: 180, h: 120 }
    g.setNode(n.id, { width: dim.w, height: dim.h })
  }
  for (const e of rawEdges) g.setEdge(e.source, e.target)
  dagre.layout(g)
  return {
    nodes: rawNodes.map((n: any) => {
      const pos = g.node(n.id)
      const dim = NODE_DIMS[n.data.nodeType] || { w: 180, h: 120 }
      return { ...n, position: { x: pos.x - dim.w / 2, y: pos.y - dim.h / 2 } }
    }),
    edges: rawEdges,
  }
}

function buildCurrentGraph() {
  if (!currentPath.value) return
  const { nodes: rn, edges: re } = buildFlowGraph(currentPath.value)
  const layouted = getLayoutedElements(rn, re)
  nodes.value = layouted.nodes
  edges.value = layouted.edges
}

// ============ Load ============
onMounted(async () => {
  const params = new URLSearchParams(window.location.search)
  const tid = parseInt(params.get('type_id') || '0')
  typeId.value = tid
  if (!tid) { loading.value = false; return }

  try {
    const res = await http.get(`/EVE/pi/products/${tid}/paths`)
    const data = await res.json()
    if (data.status === 200) {
      product.value = data.data
      currentPath.value = (data.data.all_paths || [])[0] || null
      buildCurrentGraph()
      document.title = (data.data.name_zh || 'PI产品') + ' - 生产树'
    }
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-if="loading" class="loading">加载中...</div>
  <div v-else-if="!currentPath" class="empty">未找到产品数据</div>
  <div v-else class="tree-page">
    <div class="tree-header">
      <span class="tree-title">{{ product?.name_zh }}</span>
      <span class="tree-desc">{{ currentPath.path_description }}</span>
      <span class="tree-margin" :class="marginColorClass(currentPath.profit_margin_pct)">
        利润率 {{ formatProfitMargin(currentPath.profit_margin_pct) }}
      </span>
      <span class="tree-profit">利润 {{ formatMoney(currentPath.profit) }}</span>
    </div>
    <div class="vue-flow-wrapper">
      <VueFlow v-if="nodes.length" :key="'flow-' + activePathIndex"
        v-model:nodes="nodes" v-model:edges="edges"
        :default-viewport="{ zoom: 1, x: 0, y: 0 }"
        :min-zoom="0.3" :max-zoom="2" fit-view-on-init class="pi-flow">
        <Background :gap="20" />
        <template #node-pi-node="props">
          <div class="pi-flow-node" :class="'pi-fn-' + props.data.nodeType">
            <Handle v-if="props.data.nodeType !== 'leaf'" type="target" :position="Position.Top" />
            <template v-if="props.data.nodeType === 'leaf'">
              <img :src="typeIconUrl(props.data.item.type_id)" class="pi-fn-icon" />
              <div class="pi-fn-name">{{ props.data.item.name_zh }}</div>
              <div class="pi-fn-qty">×{{ props.data.item.quantity }}</div>
              <div class="pi-fn-price">{{ formatMoney(props.data.item.unit_price) }}</div>
            </template>
            <template v-if="props.data.nodeType === 'factory'">
              <img :src="typeIconUrl(props.data.tierDetail.type_id)" class="pi-fn-icon" />
              <div class="pi-fn-name">{{ props.data.tierDetail.name_zh }}</div>
              <div class="pi-fn-tier">P{{ props.data.tierDetail.tier }}</div>
              <div class="pi-fn-divider"></div>
              <div class="pi-fn-detail">投入 {{ formatMoney(props.data.tierDetail.tier_input_cost) }}</div>
              <div class="pi-fn-detail">产出 ×{{ props.data.tierDetail.output_qty }} {{ formatMoney(props.data.tierDetail.output_price) }}/个</div>
              <div class="pi-fn-profit" :class="marginColorClass(props.data.tierDetail.tier_margin_pct)">
                {{ formatMoney(props.data.tierDetail.tier_profit) }} ({{ formatProfitMargin(props.data.tierDetail.tier_margin_pct) }})
              </div>
            </template>
            <template v-if="props.data.nodeType === 'output'">
              <img :src="typeIconUrl(props.data.outputItem.type_id)" class="pi-fn-icon" />
              <div class="pi-fn-name">{{ props.data.outputItem.name_zh }}</div>
              <div class="pi-fn-tier">产出</div>
              <div class="pi-fn-divider"></div>
              <div class="pi-fn-detail">×{{ props.data.outputItem.quantity }} {{ formatMoney(props.data.outputItem.unit_price) }}/个</div>
              <div class="pi-fn-detail">合计 {{ formatMoney(props.data.outputItem.total_revenue) }}</div>
            </template>
            <Handle v-if="props.data.nodeType !== 'output'" type="source" :position="Position.Bottom" />
          </div>
        </template>
      </VueFlow>
    </div>
  </div>
</template>

<style scoped>
.tree-page { height: 100vh; display: flex; flex-direction: column; background: var(--k-color-surface); }
.tree-header { padding: 12px 24px; display: flex; align-items: center; gap: 16px; border-bottom: 1px solid var(--k-color-border); flex-shrink: 0; }
.tree-title { font-size: 18px; font-weight: 700; color: var(--k-color-text); }
.tree-desc { font-size: 14px; color: var(--k-color-text-secondary); }
.tree-margin { font-weight: 700; padding: 2px 10px; border-radius: 4px; font-size: 14px; }
.tree-profit { font-size: 14px; color: var(--k-color-primary); font-weight: 600; }
.margin-high { color: #67c23a; background: rgba(103,194,58,0.1); }
.margin-mid { color: #e6a23c; background: rgba(230,162,60,0.1); }
.margin-low { color: #f56c6c; background: rgba(245,108,108,0.1); }
.vue-flow-wrapper { flex: 1; overflow: hidden; }
.loading, .empty { display: flex; align-items: center; justify-content: center; height: 100vh; font-size: 18px; color: var(--k-color-text-secondary); }
.pi-flow-node { background: var(--k-color-surface); border: 1px solid var(--k-color-border); border-radius: 8px; padding: 10px 12px; min-width: 120px; display: flex; flex-direction: column; align-items: center; gap: 3px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.pi-fn-leaf { background: color-mix(in srgb, var(--k-color-surface-soft) 80%, transparent); }
.pi-fn-factory { border-left: 4px solid var(--k-color-warning); min-width: 200px; }
.pi-fn-output { border-left: 4px solid var(--k-color-primary); min-width: 200px; }
.pi-fn-icon { width: 36px; height: 36px; object-fit: contain; }
.pi-fn-name { font-size: 13px; font-weight: 600; color: var(--k-color-text); text-align: center; }
.pi-fn-tier { font-size: 11px; color: var(--k-color-text-secondary); font-weight: 600; }
.pi-fn-qty { font-size: 12px; color: var(--k-color-primary); }
.pi-fn-price { font-size: 12px; color: var(--k-color-text-secondary); }
.pi-fn-divider { width: 100%; height: 1px; background: var(--k-color-border); margin: 2px 0; opacity: 0.5; }
.pi-fn-detail { font-size: 12px; color: var(--k-color-text-secondary); }
.pi-fn-profit { font-size: 13px; font-weight: 700; padding: 2px 6px; border-radius: 3px; margin-top: 2px; }
</style>
