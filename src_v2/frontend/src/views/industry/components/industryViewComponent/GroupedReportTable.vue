<script setup lang="ts">
/* eslint-disable @typescript-eslint/no-explicit-any -- 分组行沿用各视图传入的后端原始结构（历史 any 契约），P2 只做 KTable 替换，未改数据契约 */
/**
 * 分组报表表（树形数据 → 纵向排列的多张表）
 *
 * 与「流程视图」一致的标准：
 *  - 组顺序固定，永不参与排序
 *  - 组标题条：3px 主色竖条 + 组名 + 计数 + 组合计，点击折叠
 *  - 左侧吸顶锚点栏：点击跳转，滚动时高亮当前组
 *  - 所有组共享一个排序状态（sortable="custom"，点任意表头全部同步）
 *  - 唯一的滚动容器（纵向 + 横向各一条），各表共用同一宽度
 *
 * 列定义由使用方通过默认插槽传入（<el-table-column> 会渲染进每张表）。
 */
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowDown, ArrowRight } from '@element-plus/icons-vue'
import KTable from '@/components/k/KTable.vue'

export interface ReportGroup {
    key: string
    title: string
    rows: any[]
    /** 组合计（不传则按 sumProps 自动累加） */
    totalReal?: number
    totalQty?: number
}

const props = withDefaults(defineProps<{
    /** 分组数据（一级节点 = 一组） */
    groups: ReportGroup[]
    /** 表格总宽度（列宽之和），用于多表横向同步 */
    tableWidth: number
    /** 需要求和的列 prop，用于 footer 汇总行 */
    sumProps?: string[]
    /** 分组标题旁展示的合计字段 */
    totalFields?: { prop: string, label: string }[]
    /** 行 class 计算（如完成/部分满足） */
    rowClassName?: (data: { row: any, rowIndex: number }) => string
    /** 单元格 class 计算（可复制列等） */
    cellClassName?: (data: { row: any, column: any }) => string
    /** 表格字号 */
    fontSize?: string
    /** 行唯一键（不同视图可能是 row_id / type_id） */
    rowKey?: string
}>(), {
    sumProps: () => [],
    totalFields: () => [],
    rowClassName: undefined,
    cellClassName: undefined,
    fontSize: '14px',
    rowKey: 'row_id',
})

const emit = defineEmits<{
    (e: 'sort-change', payload: { prop: string, order: 'ascending' | 'descending' | '' }): void
}>()

const groupListRef = ref<HTMLElement>()
const groupRefs = new Map<string, HTMLElement>()
const collapsedGroups = ref<Set<string>>(new Set())
const activeGroup = ref('')
const sortProp = ref('')
const sortOrder = ref<'ascending' | 'descending' | ''>('')

const setGroupRef = (key: string, el: any) => {
    if (el) groupRefs.set(key, el as HTMLElement)
    else groupRefs.delete(key)
}

const formatNumber = (value: unknown): string => {
    const num = Number(value)
    if (value === null || value === undefined || value === '' || Number.isNaN(num)) return ''
    return num.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

const groupTotal = (g: ReportGroup, prop: string) => {
    if (prop === 'real_quantity' && g.totalReal !== undefined) return g.totalReal
    if (prop === 'quantity' && g.totalQty !== undefined) return g.totalQty
    return g.rows.reduce((s, r) => s + (Number(r?.[prop]) || 0), 0)
}

const sortRows = (rows: any[]) => {
    if (!sortProp.value || !sortOrder.value) return rows
    const dir = sortOrder.value === 'ascending' ? 1 : -1
    return [...rows].sort((a, b) => {
        const av = a?.[sortProp.value]
        const bv = b?.[sortProp.value]
        const an = Number(av)
        const bn = Number(bv)
        const aNum = av !== null && av !== undefined && av !== '' && !Number.isNaN(an)
        const bNum = bv !== null && bv !== undefined && bv !== '' && !Number.isNaN(bn)
        if (aNum && bNum) return (an - bn) * dir
        return String(av ?? '').localeCompare(String(bv ?? ''), 'zh-CN') * dir
    })
}

const onSortChange = ({ prop, order }: { prop: string, order: 'ascending' | 'descending' | null }) => {
    if (prop === sortProp.value && order === (sortOrder.value || null)) return
    sortProp.value = prop || ''
    sortOrder.value = order || ''
    emit('sort-change', { prop: sortProp.value, order: sortOrder.value })
}

const clearSort = () => {
    sortProp.value = ''
    sortOrder.value = ''
    emit('sort-change', { prop: '', order: '' })
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

// footer 汇总行
const summaryMethod = ({ columns, data }: { columns: any[], data: any[] }) => {
    return columns.map((col: any, index: number) => {
        if (index === 0) return '合计'
        const prop = col.property
        if (!prop || !props.sumProps.includes(prop)) return ''
        const total = (data || []).reduce((s: number, row: any) => s + (Number(row?.[prop]) || 0), 0)
        return formatNumber(total)
    })
}

// 滚动高亮当前组
let observer: IntersectionObserver | null = null
const setupObserver = () => {
    observer?.disconnect()
    const scroller = groupListRef.value?.closest('.el-tab-pane') as HTMLElement | null
    if (!scroller) return
    observer = new IntersectionObserver(
        (entries) => {
            const visible = entries.filter(e => e.isIntersecting)
            if (visible.length) activeGroup.value = (visible[0].target as HTMLElement).dataset.group || ''
        },
        { root: scroller, rootMargin: '-8% 0px -70% 0px', threshold: 0 },
    )
    groupRefs.forEach(el => observer!.observe(el))
}

watch(() => props.groups.length, async () => {
    await nextTick()
    setupObserver()
})

onMounted(async () => {
    await nextTick()
    setupObserver()
})

onUnmounted(() => {
    observer?.disconnect()
    observer = null
})

defineExpose({ clearSort })
</script>

<template>
    <div class="grouped-report">
        <nav v-if="groups.length > 1" class="group-rail" aria-label="分组跳转">
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

        <div ref="groupListRef" class="group-list">
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
                    <span v-for="f in totalFields" :key="f.prop" class="group-total">
                        {{ f.label }} <b>{{ formatNumber(groupTotal(g, f.prop)) }}</b>
                    </span>
                    <!-- 分组自定义操作（点击不触发折叠） -->
                    <span class="group-actions" @click.stop>
                        <slot name="group-action" :group="g" />
                    </span>
                </header>

                <div class="group-table-wrap" :style="{ width: tableWidth + 'px' }">
                    <KTable
                        v-show="!collapsedGroups.has(g.key)"
                        density="compact"
                        :data="sortRows(g.rows)"
                        :key="`grp-${g.key}`"
                        :row-key="rowKey"
                        :row-class-name="rowClassName"
                        :cell-class-name="cellClassName"
                        :style="{ fontSize: fontSize }"
                        :show-summary="sumProps.length > 0"
                        :summary-method="summaryMethod"
                        @sort-change="onSortChange"
                    >
                        <!-- 列定义由使用方提供 -->
                        <slot />
                    </KTable>
                </div>
            </section>
        </div>
    </div>
</template>

<style scoped>
.grouped-report {
    display: flex;
    gap: 12px;
    height: 100%;
    min-height: 0;
}

.group-rail {
    flex: 0 0 auto;
    width: 116px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px 6px;
    overflow-y: auto;
    background: var(--k-color-surface);
    border: 1px solid var(--k-color-border-subtle);
    border-radius: var(--k-radius-sm);
    box-shadow: var(--k-shadow-section);
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

/* 唯一滚动容器：纵向 + 横向都交给它，多张表共用一条横滚条 */
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

.group-section {
    background: var(--k-color-surface);
    border: 1px solid var(--k-color-border-subtle);
    border-radius: var(--k-radius-sm);
    box-shadow: var(--k-shadow-section);
    padding: 0 0 2px;
    scroll-margin-top: 8px;
}

.group-actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 6px;
}

.group-header {
    position: relative;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 14px 9px 16px;
    border-bottom: 1px solid var(--k-color-border-subtle);
    border-radius: var(--k-radius-sm) var(--k-radius-sm) 0 0;
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

.group-table-wrap {
    flex: 0 0 auto;
}
</style>
