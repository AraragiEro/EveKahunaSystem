<script setup lang="ts">
/* eslint-disable @typescript-eslint/no-explicit-any -- 表格行沿用后端原始结构（历史 any 契约），P2 只做 KTable 替换，未改数据契约 */
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, ArrowRight, Search, Grid, TrendCharts } from '@element-plus/icons-vue'
import PriceTrendCard from './PriceTrendCard.vue'
import KTable from '@/components/k/KTable.vue'
import { usePriceTrendAuto } from '@/composables/usePriceTrend'

// Props定义
const props = defineProps<{
    flowData: any[]
    selectedPlan: string | null
}>()

// 所有行的 type_id（供批量价格趋势加载）
const allTypeIds = computed(() => {
    const ids: number[] = []
    ;(props.flowData || []).forEach((g: any) => {
        ;(g?.children || []).forEach((r: any) => {
            const id = Number(r?.type_id)
            if (id > 0) ids.push(id)
        })
    })
    return ids
})
const trendCtx = usePriceTrendAuto(() => allTypeIds.value, 30, 'jita')
const trendOf = (row: any) => trendCtx.summaryOf(row?.type_id)
const trendState = (row: any) => trendCtx.stateOf(row?.type_id)
const trendPctClass = (pct: number) => (pct <= -8 ? 'num-good' : pct >= 8 ? 'num-danger' : 'num-muted')
// 搜索关键字（按物品名 / 物品id 过滤组内行）
const keyword = ref('')

// 本地存储键前缀
const FLOW_COLUMNS_STORAGE_KEY_PREFIX = 'flow_columns_'

// 分组已经表达了「层」，所以没有必须常驻的列了
const fixedColumnIds: string[] = []

// 列设置选项（不包含不可隐藏的列）
const columnOptions = [
    { id: 'type_id', label: '物品id' },
    { id: 'type_name', label: '物品名en' },
    { id: 'price_trend', label: '价格趋势' },
    { id: 'tpye_name_zh', label: '物品名zh' },
    { id: 'quantity', label: '总需求' },
    { id: 'real_quantity', label: '缺失' },
    { id: 'redundant', label: '冗余' },
    { id: 'store_quantity', label: '库存' },
    { id: 'running_jobs', label: '运行中任务' },
    { id: 'real_jobs', label: '缺失流程' },
    { id: 'jobs', label: '总流程' },
    { id: 'bp_quantity', label: '蓝图库存单位' },
    { id: 'bp_jobs', label: '蓝图库存流程' },
    { id: 'status', label: '状态' }
]

// 默认可见列（所有可隐藏的列）
const defaultVisibleColumnIds = columnOptions.map(col => col.id)


const flowColumnSettingsMap = ref<Record<string, string[]>>({})

// 保存流程列设置到本地存储
const saveFlowColumnSettings = (planName: string, visibleColumns: string[]) => {
    try {
        const key = `${FLOW_COLUMNS_STORAGE_KEY_PREFIX}${planName || 'default'}`
        localStorage.setItem(key, JSON.stringify(visibleColumns))
        // 更新内存中的 map
        flowColumnSettingsMap.value[planName || 'default'] = visibleColumns
        console.log(`流程 ${planName || 'default'} 的列设置已保存到本地`)
    } catch (error) {
        console.error('保存流程列设置失败:', error)
    }
}

// 从本地存储加载流程列设置
const loadFlowColumnSettings = (planName: string): string[] | null => {
    try {
        const key = `${FLOW_COLUMNS_STORAGE_KEY_PREFIX}${planName || 'default'}`
        const data = localStorage.getItem(key)
        if (data) {
            const parsed = JSON.parse(data) as string[]
            // 更新内存中的 map
            flowColumnSettingsMap.value[planName || 'default'] = parsed
            console.log(`从本地加载流程 ${planName || 'default'} 的列设置`)
            return parsed
        }
    } catch (error) {
        console.error('加载流程列设置失败:', error)
    }
    return null
}

// 当前计划的可见列（唯一真来源，ref 而不是 computed，避免读-写互相依赖）
const visibleColumnIds = ref<string[]>([...fixedColumnIds, ...defaultVisibleColumnIds])

// 列结构合并：新增列只要没被用户显式关闭就并入旧存档（否则老用户的存档里永远没有新列）
const COLUMNS_ADDED_IN_V2 = ['price_trend']

// 新列只要没被用户显式关闭，就应可见：以「缺列即补」判断，而不是只看全局版本号，
// 否则版本号升过一次后，后续存档仍会缺列（存档里已存的是 old 列表）。
const migrateColumnSchema = (saved: string[] | null, planName: string): string[] | null => {
    if (!saved || !saved.length) return saved
    const merged = Array.from(new Set([...saved, ...COLUMNS_ADDED_IN_V2]))
    if (merged.length !== saved.length) {
        // 回写存档，保证下次启动仍然包含新列
        saveFlowColumnSettings(planName, merged)
    }
    return merged
}

// 按计划载入列配置：内存 map → localStorage → 默认全开
const applyPlanColumns = (planName: string | null) => {
    const name = planName || 'default'
    const saved = migrateColumnSchema(flowColumnSettingsMap.value[name] || loadFlowColumnSettings(name), name)
    const userSelectedColumns = (saved && saved.length > 0)
        ? saved.filter(id => columnOptions.some(col => col.id === id))
        : defaultVisibleColumnIds
    visibleColumnIds.value = [...fixedColumnIds, ...userSelectedColumns]
}

// 监听计划切换，自动加载列设置
watch(() => props.selectedPlan, (newPlan) => {
    applyPlanColumns(newPlan)
}, { immediate: true })




// 列下拉面板：勾选即生效（同时写回本地存储）
const columnSelection = computed<string[]>({
    get: () => visibleColumnIds.value.filter(id => !fixedColumnIds.includes(id)),
    set: (val: string[]) => {
        visibleColumnIds.value = [...fixedColumnIds, ...val]
        saveFlowColumnSettings(props.selectedPlan || 'default', val)
    },
})

// 由库存/缺失派生的状态（后端 status 字段常为空，直接看数字更有用）
const stockStateOf = (row: any): { tone: string, label: string } => {
    const miss = Number(row?.real_quantity) || 0
    const stock = Number(row?.store_quantity) || 0
    if (miss <= 0) return { tone: 'ok', label: '充足' }
    if (stock <= 0) return { tone: 'danger', label: '缺料' }
    if (stock < miss) return { tone: 'warn', label: '部分' }
    return { tone: 'ok', label: '可覆盖' }
}

// 每张表底部汇总行：只合计数量类列
const summaryMethod = ({ columns, data }: { columns: any[], data: any[] }) => {
    const sumKeys = ['quantity', 'real_quantity', 'redundant', 'store_quantity', 'real_jobs', 'jobs']
    return columns.map((col: any, index: number) => {
        if (index === 0) return '合计'
        const prop = col.property
        if (!sumKeys.includes(prop)) return ''
        const total = (data || []).reduce((s: number, row: any) => s + (Number(row?.[prop]) || 0), 0)
        return formatAccounting(total)
    })
}

// 工具栏右侧的当前行数
const visibleRowCount = computed(() =>
    groups.value.reduce((s, g) => s + g.rows.length, 0),
)

// 会计格式格式化函数
const formatAccounting = (value: number | string | null | undefined): string => {
    if (value === null || value === undefined || value === '') {
        return ''
    }
    const num = typeof value === 'string' ? parseFloat(value) : value
    if (isNaN(num)) {
        return String(value)
    }
    // 使用 toLocaleString 格式化数字，添加千位分隔符
    return num.toLocaleString('zh-CN', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
    })
}

// 行样式函数
const CompleteRowClassName = (data: { row: any, rowIndex: number }) => {
    const miss = Number(data.row?.real_quantity) || 0
    const stock = Number(data.row?.store_quantity) || 0
    if (miss <= 0) return 'complete-row'
    if (stock > 0 && stock < miss) return 'partial-row'
    return 'full'
}

/* ────────────────────────────────────────────────────────────────
 * 分组分表：树形的一级节点（层 1 / 层 2）拆成纵向排列的多张表
 *  - 组的顺序永远按数据原顺序，排序不会打乱分组
 *  - 所有组共享同一个排序状态（点任意表头，全部同步）
 * ──────────────────────────────────────────────────────────────── */
const groupListRef = ref<HTMLElement>()
const groupRefs = new Map<string, HTMLElement>()
const collapsedGroups = ref<Set<string>>(new Set())
const activeGroup = ref<string>('')
const sortProp = ref<string>('')
const sortOrder = ref<'ascending' | 'descending' | ''>('')

const setGroupRef = (key: string, el: any) => {
    if (el) groupRefs.set(key, el as HTMLElement)
    else groupRefs.delete(key)
}

const groups = computed(() => {
    const list = Array.isArray(props.flowData) ? props.flowData : []
    const kw = keyword.value.trim().toLowerCase()
    const match = (r: any) => {
        if (!kw) return true
        const hay = `${r?.type_name ?? ''} ${r?.tpye_name_zh ?? ''} ${r?.type_id ?? ''}`.toLowerCase()
        return hay.includes(kw)
    }
    return list
        .map((node: any) => {
            const all: any[] = Array.isArray(node.children) ? node.children : []
            const rows = all.filter(match)
            const sum = (f: string) => rows.reduce((s, r) => s + (Number(r[f]) || 0), 0)
            return {
                key: String(node.layer_id ?? node.row_id),
                title: node.layer_id !== undefined && node.layer_id !== null ? `层 ${node.layer_id}` : (node.type_name || '未分组'),
                rows,
                totalReal: sum('real_quantity'),
                totalQty: sum('quantity'),
            }
        })
        // 没有子行（或搜索后无匹配）的层不显示
        .filter(g => g.rows.length > 0)
})

/* 所有分组表统一宽度：横向滚动交给外层一条滚动条，
   这样多张表横向同步移动，而不是每张表各有一条横滚条 */
const COLUMN_WIDTHS: Record<string, number> = {
    type_id: 90,
    type_name: 130,
    tpye_name_zh: 130,
    quantity: 110,
    real_quantity: 110,
    redundant: 110,
    store_quantity: 110,
    running_jobs: 110,
    real_jobs: 110,
    jobs: 100,
    bp_quantity: 120,
    bp_jobs: 130,
    status: 90,
}

/* ── 物品名列宽：窗口够宽时按最长文本自适应，窄窗口维持固定值 ── */
const NAME_MIN_WIDTH = 130
const NAME_MAX_WIDTH = 300
const WIDE_THRESHOLD = 1600

const windowWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1920)
const onResize = () => { windowWidth.value = window.innerWidth }

const textMeasurer = (() => {
    let ctx: CanvasRenderingContext2D | null = null
    return (text: string) => {
        if (!text) return 0
        if (!ctx) {
            const canvas = document.createElement('canvas')
            ctx = canvas.getContext('2d')
        }
        if (!ctx) return text.length * 8
        ctx.font = '14px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif'
        return ctx.measureText(text).width
    }
})()

const nameWidths = computed(() => {
    const list = groups.value.flatMap(g => g.rows)
    if (windowWidth.value < WIDE_THRESHOLD) {
        return { en: NAME_MIN_WIDTH, zh: NAME_MIN_WIDTH }
    }
    const fit = (field: 'type_name' | 'tpye_name_zh', extra: number) => {
        const widest = list.reduce((max, r) => Math.max(max, textMeasurer(String(r?.[field] ?? ''))), 0)
        return Math.min(NAME_MAX_WIDTH, Math.max(NAME_MIN_WIDTH, Math.ceil(widest) + extra))
    }
    // extra：左右内边距 24 + 趋势图标 16
    return { en: fit('type_name', 44), zh: fit('tpye_name_zh', 44) }
})
const tableWidth = computed(() => {
    const dynamic: Record<string, number> = {
        type_name: nameWidths.value.en,
        tpye_name_zh: nameWidths.value.zh,
    }
    const sum = Object.entries(COLUMN_WIDTHS).reduce(
        (acc, [id, w]) => (visibleColumnIds.value.includes(id) ? acc + (dynamic[id] ?? w) : acc),
        70, // 图标列始终显示
    )
    return Math.max(sum, 900)
})

const sortRows = (rows: any[]) => {
    if (!sortProp.value || !sortOrder.value) return rows
    const dir = sortOrder.value === 'ascending' ? 1 : -1
    return [...rows].sort((a, b) => {
        const av = a?.[sortProp.value]
        const bv = b?.[sortProp.value]
        const an = Number(av)
        const bn = Number(bv)
        const aIsNum = av !== null && av !== undefined && av !== '' && !Number.isNaN(an)
        const bIsNum = bv !== null && bv !== undefined && bv !== '' && !Number.isNaN(bn)
        if (aIsNum && bIsNum) return (an - bn) * dir
        return String(av ?? '').localeCompare(String(bv ?? ''), 'zh-CN') * dir
    })
}

const onSortChange = ({ prop, order }: { prop: string, order: 'ascending' | 'descending' | null }) => {
    // 已经处于该状态就不再处理，避免自定义排序 + 表头事件互相触发
    if (prop === sortProp.value && order === (sortOrder.value || null)) return
    sortProp.value = prop || ''
    sortOrder.value = order || ''
}

// 排序提示里显示中文列名，而不是 real_quantity 这种字段名
const sortLabel = computed(() => {
    const col = columnOptions.find(c => c.id === sortProp.value)
    return col ? col.label : sortProp.value
})

const clearSort = () => {
    sortProp.value = ''
    sortOrder.value = ''
}

const toggleGroup = (key: string) => {
    const next = new Set(collapsedGroups.value)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    collapsedGroups.value = next
}

const scrollToGroup = (key: string) => {
    const el = groupRefs.get(key)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// 滚动时高亮当前所在组
let groupObserver: IntersectionObserver | null = null
const setupGroupObserver = () => {
    groupObserver?.disconnect()
    const scroller = groupListRef.value?.closest('.el-tab-pane') as HTMLElement | null
    if (!scroller) return
    groupObserver = new IntersectionObserver(
        (entries) => {
            const visible = entries.filter(e => e.isIntersecting)
            if (!visible.length) return
            activeGroup.value = (visible[0].target as HTMLElement).dataset.group || ''
        },
        { root: scroller, rootMargin: '-8% 0px -70% 0px', threshold: 0 },
    )
    groupRefs.forEach(el => groupObserver!.observe(el))
}

watch(() => groups.value.length, async () => {
    await nextTick()
    setupGroupObserver()
})
onMounted(async () => {
    window.addEventListener('resize', onResize)
    await nextTick()
    setupGroupObserver()
})
onUnmounted(() => {
    window.removeEventListener('resize', onResize)
    groupObserver?.disconnect()
    groupObserver = null
})

// 让 td 自己承担可复制语义：底色画在 td 上才能铺满整格（画在内部 div 上会上下留白）
const COPY_COLUMNS = ['type_name', 'tpye_name_zh']
const copyCellClassName = ({ column }: { row: any, column: any }) => {
    // 只标记"这一列可以复制"；复制成功的高亮由点击时直接加到 td 上
    // （:cell-class-name 依赖的响应式值变化不会让 EP 重新渲染单元格，实测点了不生效）
    return COPY_COLUMNS.includes(column?.property) ? 'copy-col' : ''
}

// 复制成功的就地反馈：把 class 加到被点的 td 上，1.2s 后移除
const flashCopied = (td: HTMLElement | null) => {
    if (!td) return
    td.classList.add('is-copied')
    setTimeout(() => td.classList.remove('is-copied'), 1200)
}

// 复制单元格内容
const copyCellContent = async (content: string | number | null | undefined, fieldName: string = '', ev?: MouseEvent) => {
    // 必须同步取出 td：事件派发结束后 ev.currentTarget 会被置为 null
    const td = ((ev?.currentTarget || ev?.target) as HTMLElement | null)?.closest?.('td') ?? null
    try {
        if (content === null || content === undefined || content === '') {
            ElMessage.warning('没有可复制的内容')
            return
        }
        
        // 直接转换为字符串，保持原始值（数字不添加千位分隔符，方便粘贴到其他应用）
        const text = String(content)
        
        // 优先使用 Clipboard API（需要 HTTPS 或 localhost）
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text)
            ElMessage.success(`已复制${fieldName ? ` ${fieldName} ` : ' '}到剪贴板`)
            flashCopied(td)
        } else {
            // 降级方案：使用传统的 execCommand 方法
            const textarea = document.createElement('textarea')
            textarea.value = text
            textarea.style.position = 'fixed'
            textarea.style.left = '-9999px'
            textarea.style.top = '-9999px'
            document.body.appendChild(textarea)
            textarea.select()
            textarea.setSelectionRange(0, text.length) // 兼容移动设备
            
            try {
                const successful = document.execCommand('copy')
                if (successful) {
                    ElMessage.success(`已复制${fieldName ? ` ${fieldName} ` : ' '}到剪贴板`)
            flashCopied(td)
                } else {
                    throw new Error('execCommand 复制失败')
                }
            } finally {
                document.body.removeChild(textarea)
            }
        }
    } catch (error) {
        console.error('复制失败:', error)
        ElMessage.error('复制失败，请重试')
    }
}

</script>

<template>
    <div class="flow-view-container">
        <!-- 工具栏 -->
        <div class="flow-toolbar">
            <el-input
                v-model="keyword"
                class="flow-search"
                size="small"
                clearable
                placeholder="搜索物品名 / 物品id"
                :prefix-icon="Search"
            />
            <el-popover placement="bottom-start" :width="210" trigger="click" popper-class="flow-col-popper">
                <template #reference>
                    <el-button size="small" :icon="Grid">列</el-button>
                </template>
                <div class="flow-col-panel">
                    <div class="flow-col-title">显示列</div>
                    <el-checkbox-group v-model="columnSelection" class="flow-col-list">
                        <el-checkbox v-for="col in columnOptions" :key="col.id" :value="col.id">
                            {{ col.label }}
                        </el-checkbox>
                    </el-checkbox-group>
                </div>
            </el-popover>
            <span v-if="sortProp" class="sort-indicator">
                排序：{{ sortLabel }} {{ sortOrder === 'descending' ? '↓' : '↑' }}
                <el-button link size="small" @click="clearSort">清除</el-button>
            </span>
            <span class="flow-count">{{ visibleRowCount }} 项</span>
        </div>

        <!-- 左：分组锚点；右：分组表纵向堆叠 -->
        <div class="flow-split">
            <nav class="group-rail" aria-label="分组跳转">
                <button
                    v-for="g in groups"
                    :key="g.key"
                    type="button"
                    class="rail-item"
                    :class="{ active: activeGroup === g.key }"
                    @click="scrollToGroup(g.key)"
                >
                    <span class="rail-name">{{ g.title }}</span>
                    <span class="rail-count">{{ g.rows.length }}</span>
                </button>
            </nav>

            <div class="group-list" ref="groupListRef">
                <section
                    v-for="g in groups"
                    :key="g.key"
                    class="group-section"
                    :data-group="g.key"
                    :ref="(el: any) => setGroupRef(g.key, el)"
                >
                    <header class="group-header" @click="toggleGroup(g.key)">
                        <el-icon class="group-caret">
                            <ArrowRight v-if="collapsedGroups.has(g.key)" />
                            <ArrowDown v-else />
                        </el-icon>
                        <span class="group-name">{{ g.title }}</span>
                        <span class="group-count">{{ g.rows.length }} 项</span>
                        <span class="group-total">缺失合计 <b>{{ formatAccounting(g.totalReal) }}</b></span>
                        <span class="group-total">总需求 <b>{{ formatAccounting(g.totalQty) }}</b></span>
                    </header>

                    <div class="group-table-wrap" :style="{ width: tableWidth + 'px' }">
                    <KTable
                        v-show="!collapsedGroups.has(g.key)"
                        class="flow-data-table"
                        density="compact"
                        :data="sortRows(g.rows)"
                        :key="`flow-table-${selectedPlan || 'default'}-${g.key}`"
                        row-key="row_id"
                        :row-class-name="CompleteRowClassName"
                        style="font-size: 14px;"
                        show-summary
                        :summary-method="summaryMethod"
                        :cell-class-name="copyCellClassName"
                        @sort-change="onSortChange"
                    >
        <el-table-column label="图标" prop="type_id" width="70" fixed="left">
            <template #default="{ row }">
            <img 
                v-if="row?.type_id"
                :src="`https://imageserver.eveonline.com/types/${row.type_id}/icon`" 
                alt="类型" 
                width="30" 
                height="30"
                style="border-radius: 4px;" 
                loading="lazy"
            />
            </template>
        </el-table-column>
        <el-table-column v-if="visibleColumnIds.includes('type_id')" label="物品id" prop="type_id" width="90" fixed="left"/>
        <el-table-column v-if="visibleColumnIds.includes('type_name')" label="物品名en" prop="type_name" :width="nameWidths.en" fixed="left">
            <template #default="{ row }">
                <div
                    class="copyable-cell"
                    @click="copyCellContent(row.type_name, '物品名en', $event)"
                    :title="`点击复制: ${row.type_name || ''}`"
                >
                    <span class="copyable-text">{{ row.type_name }}</span>

                </div>
            </template>
        </el-table-column>
        <el-table-column v-if="visibleColumnIds.includes('tpye_name_zh')" label="物品名zh" prop="tpye_name_zh" :width="nameWidths.zh">
            <template #default="{ row }">
                <div class="name-with-trend">
                    <div
                        class="copyable-cell"
                        @click="copyCellContent(row.tpye_name_zh, '物品名zh', $event)"
                        :title="`点击复制: ${row.tpye_name_zh || ''}`"
                    >
                        <span class="copyable-text">{{ row.tpye_name_zh }}</span>
                    </div>
                    <!-- 价格趋势：JITA 30 天最高/最低价区间 + 涨跌建议（hover 才请求） -->
                    <el-popover
                        v-if="row.type_id"
                        trigger="hover"
                        placement="right"
                        :width="300"
                        :show-after="160"
                        popper-class="price-trend-pop"
                    >
                        <template #reference>
                            <el-icon class="trend-icon" @click.stop title="查看 JITA 价格趋势">
                                <TrendCharts />
                            </el-icon>
                        </template>
                        <PriceTrendCard
                            :summary="trendOf(row)"
                            :label="row.tpye_name_zh || row.type_name"
                            :days="30"
                        />
                    </el-popover>
                </div>
            </template>
        </el-table-column>
        <el-table-column v-if="visibleColumnIds.includes('price_trend')" label="价格趋势" width="150">
            <template #default="{ row }">
                <div class="trend-cell">
                    <template v-if="trendState(row) === 'ok'">
                        <svg class="trend-spark" viewBox="0 0 70 22" preserveAspectRatio="none">
                            <path :d="trendCtx.sparkPaths(trendOf(row)).band" class="spark-band" />
                            <path :d="trendCtx.sparkPaths(trendOf(row)).line" class="spark-line" />
                        </svg>
                        <span class="trend-pct" :class="trendPctClass(trendOf(row)?.pct || 0)">
                            {{ ((trendOf(row)?.pct || 0) >= 0 ? '+' : '') + (trendOf(row)?.pct || 0).toFixed(1) + '%' }}
                        </span>
                    </template>
                    <span v-else-if="trendState(row) === 'collecting'" class="trend-state">采集…</span>
                    <span v-else class="trend-state">数据缺失</span>
                </div>
            </template>
        </el-table-column>
        <el-table-column v-if="visibleColumnIds.includes('quantity')" label="总需求" prop="quantity" width="110" align="right" sortable="custom" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column v-if="visibleColumnIds.includes('real_quantity')" label="缺失" prop="real_quantity" width="110" align="right" sortable="custom">
            <template #default="{ row }">
                <span class="num-cell" :class="Number(row?.real_quantity) > 0 ? 'num-danger' : 'num-muted'">{{ formatAccounting(row?.real_quantity) }}</span>
            </template>
        </el-table-column>
        <el-table-column v-if="visibleColumnIds.includes('redundant')" label="冗余" prop="redundant" width="110" align="right" sortable="custom" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column v-if="visibleColumnIds.includes('store_quantity')" label="库存" prop="store_quantity" width="110" align="right" sortable="custom">
            <template #default="{ row }">
                <span class="num-cell" :class="Number(row?.store_quantity) > 0 ? 'num-good' : 'num-muted'">{{ formatAccounting(row?.store_quantity) }}</span>
            </template>
        </el-table-column>
        <el-table-column v-if="visibleColumnIds.includes('running_jobs')" label="运行中任务" prop="running_jobs"/>
        <el-table-column v-if="visibleColumnIds.includes('real_jobs')" label="缺失流程" prop="real_jobs" align="right" sortable="custom" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column v-if="visibleColumnIds.includes('jobs')" label="总流程" prop="jobs" align="right" sortable="custom" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column v-if="visibleColumnIds.includes('bp_quantity')" label="蓝图库存单位" prop="bp_quantity" align="right" sortable="custom" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column v-if="visibleColumnIds.includes('bp_jobs')" label="蓝图库存流程" prop="bp_jobs">
            <template #default="{ row }">
                <template v-if="row?.bp_jobs">
                    <span v-if="Number(row?.bp_jobs?.bpc)> 0">
                        {{ Number(row?.bp_jobs?.bpc) }} 流程拷贝
                    </span>
                    <span v-if="Number(row?.bp_jobs?.bpc)> 0 && Number(row?.bp_jobs?.bpo)> 0">，</span>
                    <span v-if="Number(row?.bp_jobs?.bpo)> 0">
                        {{ Number(row?.bp_jobs?.bpo) }} 份原图
                    </span>
                </template>
            </template>
        </el-table-column>
        <el-table-column v-if="visibleColumnIds.includes('status')" label="状态" prop="status" width="96" align="center" fixed="right">
            <template #default="{ row }">
                <span class="status-pill" :class="`status-${stockStateOf(row).tone}`">{{ stockStateOf(row).label }}</span>
            </template>
        </el-table-column>
                    </KTable>
                    </div>
                </section>
            </div>
        </div>

    </div>
</template>

<style scoped>
.flow-view-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
}

.flow-toolbar {
    flex: 0 0 auto;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 10px;
}

.sort-indicator {
    font-size: var(--k-font-xs);
    color: var(--k-color-text-secondary);
}

/* 左：锚点栏   右：分组表 */
.flow-split {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    gap: 12px;
}

.group-rail {
    flex: 0 0 auto;
    width: 116px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px 6px;
    background: var(--k-color-surface);
    border: 1px solid var(--k-color-border-subtle);
    border-radius: var(--k-radius-md);
    box-shadow: var(--k-shadow-section);
    overflow-y: auto;
}

.rail-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 6px 8px;
    border: 1px solid transparent;
    border-radius: var(--k-radius-sm);
    background: transparent;
    color: var(--k-color-text-secondary);
    font-size: var(--k-font-xs);
    cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.rail-item:hover {
    background: var(--k-color-surface-soft);
    color: var(--k-color-text);
}

.rail-item.active {
    background: var(--k-color-primary-soft);
    border-color: color-mix(in srgb, var(--k-color-primary) 42%, var(--k-color-border));
    color: var(--k-color-primary);
    font-weight: 600;
}

.rail-name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.rail-count {
    flex: 0 0 auto;
    font-variant-numeric: tabular-nums;
    opacity: 0.75;
}

/* 唯一的滚动容器：纵向滚 + 横向滚（多张表共用一条横滚条） */
.group-list {
    flex: 1 1 auto;
    min-width: 0;
    min-height: 0;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 2px 4px 14px 2px;
}

/* 每个分组 = 一张模块卡片：底色比页面底亮一档 + 细边框 + 投影 + 圆角 */
.group-section {
    scroll-margin-top: 8px;
    background: var(--k-color-surface);
    border: 1px solid var(--k-color-border-subtle);
    border-radius: var(--k-radius-md);
    box-shadow: var(--k-shadow-section);
    padding: 0 0 2px;
}

/* 卡片头：左侧主色竖条 + 标题 + 计数胶囊 + 合计 */
.group-header {
    position: relative;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 14px 9px 16px;
    border-bottom: 1px solid var(--k-color-border-subtle);
    border-radius: var(--k-radius-md) var(--k-radius-md) 0 0;
    /* 用 strong 档：深色下比表体明显亮一档，浅色下也够灰 */
    background: var(--k-color-surface-strong);
    cursor: pointer;
    user-select: none;
    transition: background 0.15s ease;
}

.group-header:hover {
    background: color-mix(in srgb, var(--k-color-surface-strong) 82%, var(--k-color-primary));
}

.group-header::before {
    content: '';
    position: absolute;
    left: 6px;
    top: 9px;
    bottom: 9px;
    width: 3px;
    border-radius: var(--k-radius-pill);
    background: var(--k-color-primary);
}

.group-caret {
    color: var(--k-color-text-secondary);
    font-size: 12px;
}

.group-name {
    font-size: var(--k-font-md);
    font-weight: 600;
    color: var(--k-color-text);
}

.group-count {
    padding: 1px 8px;
    border-radius: var(--k-radius-pill);
    background: var(--k-color-primary-soft);
    color: var(--k-color-primary);
    font-size: var(--k-font-xs);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}

.group-total {
    font-size: var(--k-font-xs);
    color: var(--k-color-text-secondary);
    font-variant-numeric: tabular-nums;
}

.group-total b {
    color: var(--k-color-text);
    font-weight: 600;
}

/* ── 表头吸顶 ─────────────────────────────────────────────────────────
   EP 的 .el-table / .el-table__inner-wrapper 带 overflow:hidden，
   会阻断 sticky，必须放开；本视图表格不设固定高度，也没有表内滚动，
   所以放开 overflow 不影响滚动条。
   ─────────────────────────────────────────────────────────────────── */
.flow-view-container :deep(.el-table),
.flow-view-container :deep(.el-table__inner-wrapper),
/* 冻结列（position:sticky）只有在没有任何祖先裁剪时，才会吸附到外层 .group-list 的滚动边缘 */
.flow-view-container :deep(.el-table__body-wrapper),
.flow-view-container :deep(.el-table__body-wrapper .el-scrollbar),
.flow-view-container :deep(.el-table__body-wrapper .el-scrollbar__wrap),
.flow-view-container :deep(.el-table__footer-wrapper .el-scrollbar__wrap) {
    overflow: visible;
}

/* z-index 必须高于冻结列（EP 给 fixed 单元格的是 2），否则滚动的行会画到表头上面 */
.flow-view-container :deep(.el-table__header-wrapper) {
    position: sticky;
    top: 0;
    z-index: 4;
    background: var(--k-color-surface);
}

.flow-view-container :deep(.el-table__footer-wrapper) {
    position: relative;
    z-index: 2;
    background: var(--k-color-surface-soft);
}

/* ── 现代化表格外观 ──────────────────────────────────────────────── */
/* 去掉所有竖向格线，只留极淡的行分隔（shadcn / Linear 的做法） */
.flow-view-container :deep(.el-table) {
    --el-table-border-color: transparent;
    --el-table-border: none;
    --el-table-header-bg-color: var(--k-color-surface-soft);
    --el-table-row-hover-bg-color: transparent;
}

.flow-view-container :deep(.el-table td.el-table__cell),
.flow-view-container :deep(.el-table th.el-table__cell) {
    border-bottom: 1px solid color-mix(in srgb, var(--k-color-border) 42%, transparent);
}

/* 表头：小一号、次要色、字重 600（现代表格表头都弱于数据） */
.flow-view-container :deep(.el-table th.el-table__cell) {
    font-size: var(--k-font-xs);
    font-weight: 600;
    color: var(--k-color-text-secondary);
    letter-spacing: 0.02em;
    border-bottom: 1px solid color-mix(in srgb, var(--k-color-border) 78%, transparent);
}

/* 行首状态条只标记「部分满足」（有库存但不够）这种中间态，
   全员缺料时不染色，否则每行同色等于没有信息 */
.flow-view-container :deep(.el-table__body tr.partial-row > td.el-table__cell:first-child) {
    box-shadow: inset 3px 0 0 0 var(--k-color-warning);
}

/* 数字单元格 */
.num-cell {
    font-variant-numeric: tabular-nums;
}

.num-danger { color: var(--k-color-danger); font-weight: 600; }
.num-good { color: var(--k-color-success); }
.num-muted { color: var(--k-color-text-secondary); }

/* 状态胶囊 */
.status-pill {
    display: inline-block;
    min-width: 40px;
    padding: 1px 8px;
    border-radius: var(--k-radius-pill);
    font-size: var(--k-font-xs);
    font-weight: 600;
    line-height: 18px;
    text-align: center;
}

.status-ok {
    color: var(--k-color-success);
    background: color-mix(in srgb, var(--k-color-success) 14%, transparent);
}

.status-warn {
    color: var(--k-color-warning);
    background: color-mix(in srgb, var(--k-color-warning) 16%, transparent);
}

.status-danger {
    color: var(--k-color-danger);
    background: color-mix(in srgb, var(--k-color-danger) 14%, transparent);
}

/* 工具栏：搜索框 + 列下拉 + 计数 */
.flow-search {
    width: 220px;
}

.flow-count {
    margin-left: auto;
    font-size: var(--k-font-xs);
    color: var(--k-color-text-secondary);
    font-variant-numeric: tabular-nums;
}

/* 汇总行：弱化，只强调数字 */
.flow-view-container :deep(.el-table__footer-wrapper td.el-table__cell) {
    background: var(--k-color-surface-soft);
    font-weight: 600;
    font-size: var(--k-font-xs);
    color: var(--k-color-text-secondary);
}

/* 圆角收到 8px（Linear 的规则：矩形容器不超过 8px） */
.group-section,
.group-rail {
    border-radius: var(--k-radius-sm);
}

.group-header {
    border-radius: var(--k-radius-sm) var(--k-radius-sm) 0 0;
}
/* 斑马纹：让行之间靠底色差区分，而不是全靠格子线 */
.flow-view-container :deep(.el-table__body tr:nth-child(even) > td.el-table__cell) {
    background: color-mix(in srgb, var(--k-color-surface-soft) 62%, var(--k-color-surface));
}

.flow-view-container :deep(.el-table__body tr:hover > td.el-table__cell) {
    background: color-mix(in srgb, var(--k-color-primary) 12%, var(--k-color-surface));
}

/* 表格与卡片边框重合，避免出现双层线；内部格线用更淡的边色 */
.flow-view-container :deep(.el-table--border)::before,
.flow-view-container :deep(.el-table--border)::after {
    display: none;
}

.flow-view-container :deep(.el-table) {
    --el-table-border-color: var(--k-color-border-subtle);
}

/* 固定宽度的表容器：宽度由列宽总和决定，横向滚动由 .group-list 统一负责 */
.group-table-wrap {
    flex: 0 0 auto;
}

.flow-data-table {
    width: 100%;
}

/* 已满足目标的行：整行淡绿强调（token 混合，深浅色都可读） */
:deep(.el-table__body tr.complete-row),
:deep(.el-table__body tr.complete-row> td.el-table__cell),
:deep(.el-table__body tr.complete-row:hover> td.el-table__cell) {
    background-color: color-mix(in srgb, var(--k-color-success) 18%, var(--k-color-surface));
    font-weight: bold;
    color: var(--k-color-text);
}



/* 可复制单元格：底色画在 td 上才能正好铺满整格（画在内部 div 上会上下留 11px 白边，
   看起来像格子里浮了一块）。内部 div 只负责命中区和省略号。 */
.copyable-cell {
    cursor: pointer;
    user-select: none;
}

.copyable-text {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.flow-view-container :deep(.el-table__body tr td.copy-col) {
    cursor: pointer;
    transition: background-color 0.15s ease;
}

/* hover：整格填充 + 圆角（和单元格等大，但四角圆润，不像硬邦邦的方块） */
.flow-view-container :deep(.el-table__body tr td.copy-col:hover) {
    background: color-mix(in srgb, var(--k-color-primary) 16%, transparent);
    border-radius: var(--k-radius-sm);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--k-color-primary) 32%, transparent);
}

/* 复制成功：整格淡绿 + 文字变绿 */
.flow-view-container :deep(.el-table__body tr td.copy-col.is-copied) {
    background: color-mix(in srgb, var(--k-color-success) 18%, transparent);
    border-radius: var(--k-radius-sm);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--k-color-success) 34%, transparent);
}

.flow-view-container :deep(.el-table__body tr td.copy-col.is-copied .copyable-text) {
    color: var(--k-color-success);
}

/* 物品名 + 趋势入口：文字必须能收缩，否则长名字会把图标挤出格子（被 .cell 的 overflow 裁掉） */
.name-with-trend {
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
    max-width: 100%;
}

.name-with-trend .copyable-cell {
    flex: 1 1 auto;
    min-width: 0;
}

.name-with-trend .copyable-text {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.trend-icon {
    flex: 0 0 auto;
    cursor: pointer;
    color: var(--k-color-text-secondary);
    opacity: 0.6;
    transition: color 0.15s ease, opacity 0.15s ease;
}

.trend-icon:hover {
    color: var(--k-color-primary);
    opacity: 1;
}

/* 表内迷你趋势（平均价折线 + 高低带） */
.trend-cell {
    display: flex;
    align-items: center;
    gap: 6px;
}

.trend-spark {
    width: 70px;
    height: 22px;
    flex: 0 0 auto;
}

.spark-band {
    fill: color-mix(in srgb, var(--k-color-primary) 16%, transparent);
    stroke: none;
}

.spark-line {
    fill: none;
    stroke: color-mix(in srgb, var(--k-color-primary) 80%, transparent);
    stroke-width: 1.2;
    vector-effect: non-scaling-stroke;
}

.trend-state {
    font-size: var(--k-font-xs);
    color: var(--k-color-text-secondary);
    opacity: 0.7;
}

.trend-pct {
    font-size: var(--k-font-xs);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}
</style>

<!-- :global() 在 scoped 块里会丢弃类选择器（编译成 [data-theme=dark] 直接命中 html），
     所以深色覆盖必须写在独立的非 scoped <style> 里 -->
