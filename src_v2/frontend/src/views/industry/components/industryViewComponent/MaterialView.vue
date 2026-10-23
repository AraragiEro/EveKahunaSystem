<script setup lang="ts">
import { computed } from 'vue'
import { flashCopied, createCopyCellClassName } from '@/composables/useCopyCell'
import GroupedReportTable from './GroupedReportTable.vue'
import PriceTrendCard from './PriceTrendCard.vue'
import { usePriceTrendAuto } from '@/composables/usePriceTrend'
import { TrendCharts } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

// Props定义
const props = defineProps<{
    materialData: any[]
    selectedPlan: string | null
}>()

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


// 复制单元格内容
// 树形数据 → 分组：一级节点是「类型」（矿物/冰矿产物/…）
const groups = computed(() => {
    const list = Array.isArray(props.materialData) ? props.materialData : []
    return list
        .map((node: any) => ({
            key: String(node.row_id ?? node.layer_id),
            title: node.layer_id || '未分组',
            rows: Array.isArray(node.children) ? node.children : [],
            totalReal: (node.children || []).reduce((s: number, r: any) => s + (Number(r?.real_quantity) || 0), 0),
            totalQty: (node.children || []).reduce((s: number, r: any) => s + (Number(r?.quantity) || 0), 0),
        }))
        .filter(g => g.rows.length > 0)
})

// 价格趋势：批量拉取本视图所有物品的 JITA 30 天加权均价摘要
const allTypeIds = computed(() => {
    const ids: number[] = []
    groups.value.forEach((g: any) => (g.rows || []).forEach((r: any) => {
        const id = Number(r?.type_id)
        if (id > 0) ids.push(id)
    }))
    return ids
})
const trendCtx = usePriceTrendAuto(() => allTypeIds.value, 30, 'jita')
const trendOf = (row: any) => trendCtx.summaryOf(row?.type_id)
const trendPctClass = (pct: number) => (pct <= -8 ? 'num-good' : pct >= 8 ? 'num-danger' : 'num-muted')
const TABLE_WIDTH = 1290
const SUM_PROPS = ['real_quantity', 'quantity', 'store_quantity']
const TOTAL_FIELDS = [
    { prop: 'real_quantity', label: '缺失合计' },
    { prop: 'quantity', label: '总需求' },
]
// 可复制列标记（复制成功的高亮由 flashCopied 直接加在 td 上）
const copyCellClassName = createCopyCellClassName(['type_name', 'tpye_name_zh'])

const copyCellContent = async (content: string | number | null | undefined, fieldName: string = '', ev?: MouseEvent) => {
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
            flashCopied(ev)
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
            flashCopied(ev)
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
    <GroupedReportTable
        :groups="groups"
        :table-width="TABLE_WIDTH"
        :sum-props="SUM_PROPS"
        :total-fields="TOTAL_FIELDS"
        :cell-class-name="copyCellClassName"
    >
        <el-table-column label="类型" prop="layer_id" width="110">
        </el-table-column>
        <el-table-column label="图标" prop="type_id" width="70">
            <template #default="{ row }">
            <img 
                v-if="row?.type_id"
                :src="`https://imageserver.eveonline.com/types/${row.type_id}/icon`" 
                alt="类型" 
                width="40" 
                height="40"
                style="border-radius: 4px;" 
                loading="lazy"
            />
            </template>
        </el-table-column>
        <el-table-column label="物品id" prop="type_id" width="90"/>
        <el-table-column label="物品名en" prop="type_name" width="200">
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.type_name, '物品名en', $event)"
                    :title="`点击复制: ${row.type_name || ''}`"
               >
                    {{ row.type_name }}
                </div>
            </template>
        </el-table-column>
        <el-table-column label="物品名zh" prop="tpye_name_zh" width="200">
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.tpye_name_zh, '物品名zh', $event)"
                    :title="`点击复制: ${row.tpye_name_zh || ''}`"
               >
                    {{ row.tpye_name_zh }}
                </div>
            </template>
        </el-table-column>
        <el-table-column label="价格趋势" width="170">
            <template #default="{ row }">
                <div class="trend-cell">
                    <template v-if="trendCtx.stateOf(row?.type_id) === 'ok'">
                        <svg class="trend-spark" viewBox="0 0 70 22" preserveAspectRatio="none">
                            <path :d="trendCtx.sparkPaths(trendOf(row)).band" class="spark-band" />
                            <path :d="trendCtx.sparkPaths(trendOf(row)).line" class="spark-line" />
                        </svg>
                        <span class="trend-pct" :class="trendPctClass(trendOf(row)?.pct || 0)">
                            {{ ((trendOf(row)?.pct || 0) >= 0 ? '+' : '') + (trendOf(row)?.pct || 0).toFixed(1) + '%' }}
                        </span>
                        <el-popover trigger="hover" placement="left" :width="300" :show-after="160" popper-class="price-trend-pop">
                            <template #reference>
                                <el-icon class="trend-icon"><TrendCharts /></el-icon>
                            </template>
                            <PriceTrendCard :summary="trendOf(row)" :label="row?.tpye_name_zh || row?.type_name" :days="30" />
                        </el-popover>
                    </template>
                    <span v-else-if="trendCtx.stateOf(row?.type_id) === 'collecting'" class="trend-state">采集…</span>
                    <span v-else class="trend-state">数据缺失</span>
                </div>
            </template>
        </el-table-column>        <el-table-column label="缺失" prop="real_quantity" width="150" align="right" sortable="custom">
            <template #default="{ row }">
                <span class="num-cell" :class="Number(row?.real_quantity) > 0 ? 'num-danger' : 'num-muted'">{{ formatAccounting(row?.real_quantity) }}</span>
            </template>
        </el-table-column>
        <el-table-column label="总需求" prop="quantity" width="150" align="right" sortable="custom" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column label="库存" prop="store_quantity" width="150" align="right" sortable="custom">
            <template #default="{ row }">
                <span class="num-cell" :class="Number(row?.store_quantity) > 0 ? 'num-good' : 'num-muted'">{{ formatAccounting(row?.store_quantity) }}</span>
            </template>
        </el-table-column>
    </GroupedReportTable>
</template>

<style scoped>

/* 表内迷你趋势（与流程视图一致） */
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

.trend-pct {
    font-size: var(--k-font-xs);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}

.trend-icon {
    flex: 0 0 auto;
    cursor: pointer;
    color: var(--k-color-text-secondary);
    opacity: 0.6;
}

.trend-icon:hover {
    color: var(--k-color-primary);
    opacity: 1;
}

.trend-state {
    font-size: var(--k-font-xs);
    color: var(--k-color-text-secondary);
    opacity: 0.7;
}
</style>

<style>

/* 表内迷你趋势（与流程视图一致） */
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

.trend-pct {
    font-size: var(--k-font-xs);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}

.trend-icon {
    flex: 0 0 auto;
    cursor: pointer;
    color: var(--k-color-text-secondary);
    opacity: 0.6;
}

.trend-icon:hover {
    color: var(--k-color-primary);
    opacity: 1;
}

.trend-state {
    font-size: var(--k-font-xs);
    color: var(--k-color-text-secondary);
    opacity: 0.7;
}
</style>
