<script setup lang="ts">
/* eslint-disable @typescript-eslint/no-explicit-any -- 采购树沿用后端原始结构（历史 any 契约），P2 只做 KStat 收敛，未改数据契约 */
import GroupedReportTable from './GroupedReportTable.vue'
import KStat from '@/components/k/KStat.vue'
import { flashCopied, createCopyCellClassName } from '@/composables/useCopyCell'
import { computed, ref, watch } from 'vue'
import { http } from '@/http'
import { ElMessage } from 'element-plus'
import { CopyDocument } from '@element-plus/icons-vue'

// Props定义
const props = defineProps<{
    materialData: any[]
    selectedPlan: string | null
}>()

// 递归过滤树结构，只保留 real_quantity> 0 的节点
const filterTreeByRealQuantity = (nodes: any[]): any[] => {
    return nodes.map((node: any) => {
        // 如果有 children，递归过滤子节点
        if (node.children && Array.isArray(node.children) && node.children.length> 0) {
            const filteredChildren = filterTreeByRealQuantity(node.children)
            // 如果过滤后还有子节点，保留该节点（但只保留过滤后的子节点）
            if (filteredChildren.length> 0) {
                return {
                    ...node,
                    children: filteredChildren
                }
            }
        }
        // 检查节点本身的 real_quantity（可能是叶子节点，或者顶层节点本身也有 real_quantity）
        if (node.real_quantity !== undefined && node.real_quantity> 0) {
            return node
        }
        // 不满足条件，返回 null（后续会被过滤掉）
        return null
    }).filter((node: any) => node !== null) // 过滤掉 null 值
}

// 采购视图过滤后的数据（只显示 real_quantity> 0 的行，保持树结构）
const filteredPurchaseTableView = computed(() => {
    return filterTreeByRealQuantity(props.materialData)
})



// 递归提取树结构中的物品名和缺失数量
const extractPurchaseData = (nodes: any[]): Array<{ type_name: string, real_quantity: number }> => {
    const result: Array<{ type_name: string, real_quantity: number }> = []
    
    nodes.forEach((node: any) => {
        // 如果有 children，递归处理子节点
        if (node.children && Array.isArray(node.children) && node.children.length> 0) {
            result.push(...extractPurchaseData(node.children))
        }
        // 如果是叶子节点且有 real_quantity，添加到结果中
        if (node.type_name && node.real_quantity !== undefined && node.real_quantity> 0) {
            result.push({
                type_name: node.type_name,
                real_quantity: node.real_quantity
            })
        }
    })
    
    return result
}

// 会计格式格式化函数
const formatAccounting = (value: number | string | null | undefined): string => {
    if (value === null || value === undefined || value === '') {
        return '0'
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

// 复制单元格内容
// 4H（FRT）出单价：一次批量从 Redis 快照读取
const market4HPrices = ref<Record<string, { frt_sell: number, jita_sell: number }>>({})
const load4HPrices = async () => {
    const ids: number[] = []
    ;(Array.isArray(props.materialData) ? props.materialData : []).forEach((node: any) => {
        ;(node?.children || []).forEach((r: any) => {
            const id = Number(r?.type_id)
            if (id > 0) ids.push(id)
        })
    })
    if (!ids.length) return
    try {
        const res = await http.post('/EVE/industry/getMarket4HPrices', { type_ids: Array.from(new Set(ids)) })
        market4HPrices.value = (res?.data?.data ?? {}) as Record<string, { frt_sell: number, jita_sell: number }>
    } catch (e) {
        console.error('获取 4H 价格失败', e)
    }
}
watch(() => props.materialData, () => { void load4HPrices() }, { immediate: true })

const frtSellOf = (row: any) => Number(market4HPrices.value[String(row?.type_id)]?.frt_sell) || 0
// 与 JITA 出单价的差值（正=4H 更贵）与百分比
const frtDiffOf = (row: any) => frtSellOf(row) - (Number(row?.sell_price) || 0)

// 树形数据 → 分组：一级节点是「类型」
const groups = computed(() => {
    const list = Array.isArray(props.materialData) ? props.materialData : []
    return list
        .map((node: any) => ({
            key: String(node.type_id ?? node.layer_id),
            title: node.layer_id || '未分组',
            // 采购清单只关心真的缺料的物料；顺便把三个总价算成行字段，
            // 这样列才有 prop —— 能排序、能进 footer 汇总，不必再塞进表头
            rows: (Array.isArray(node.children) ? node.children : [])
                .filter((r: any) => Number(r?.real_quantity) > 0)
                .map((r: any) => {
                    const qty = Number(r?.real_quantity) || 0
                    const sell = (Number(r?.sell_price) || 0) * qty
                    const buy = (Number(r?.buy_price) || 0) * qty
                    return { ...r, sell_total: sell, buy_total: buy, diff_total: sell - buy, frt_sell: Number(market4HPrices.value[String(r?.type_id)]?.frt_sell) || 0 }
                }),
            totalReal: (node.children || []).reduce((s: number, r: any) => s + (Number(r?.real_quantity) || 0), 0),
        }))
        .filter(g => g.rows.length > 0)
})

// 全局合计：从分组行里汇总（与表格/footer 同源，避免两套口径）
const allPurchaseRows = computed(() => groups.value.flatMap((g: any) => g.rows || []))
const jitaSellTotalPrice = computed(() =>
    allPurchaseRows.value.reduce((s: number, r: any) => s + (Number(r?.sell_total) || 0), 0)
)
const jitaBuyTotalPrice = computed(() =>
    allPurchaseRows.value.reduce((s: number, r: any) => s + (Number(r?.buy_total) || 0), 0)
)
const TABLE_WIDTH = 1520
const SUM_PROPS = ['real_quantity', 'sell_total', 'buy_total', 'diff_total']
const TOTAL_FIELDS = [{ prop: 'real_quantity', label: '缺失合计' }]
// 可复制列标记（复制成功的高亮由 flashCopied 直接加在 td 上）
const copyCellClassName = createCopyCellClassName(['type_name', 'tpye_name_zh', 'real_quantity'])

const copyCellContent = async (content: string | number | null | undefined, fieldName: string = '', ev?: MouseEvent) => {
    try {
        if (content === null || content === undefined || content === '') {
            ElMessage.warning('没有可复制的内容')
            return
        }
        
        // 直接转换为字符串，保持原始值（数字不添加千位分隔符，方便粘贴到其他应用）
        const text = String(content)
        
        // 复制到剪贴板
        await navigator.clipboard.writeText(text)
        ElMessage.success(`已复制${fieldName ? ` ${fieldName} ` : ' '}到剪贴板`)
            flashCopied(ev)
    } catch (error) {
        console.error('复制失败:', error)
        ElMessage.error('复制失败，请重试')
    }
}

// 单组复制采购清单（只复制该分组的行）
const copyGroupPurchaseList = async (group: any) => {
    try {
        const rows = (group?.rows || []).filter((r: any) => Number(r?.real_quantity) > 0)
        if (!rows.length) {
            ElMessage.warning('该分组没有可复制的内容')
            return
        }
        const text = rows
            .map((r: any) => `${r.type_name}\t${r.real_quantity}`)
            .join('\n')
        await navigator.clipboard.writeText(text)
        ElMessage.success(`已复制「${group.title}」${rows.length} 条到剪贴板`)
    } catch (error) {
        console.error('复制失败:', error)
        ElMessage.error('复制失败，请重试')
    }
}
// 复制采购清单
const copyPurchaseList = async () => {
    try {
        // 从过滤后的数据中提取物品名和缺失数量
        const purchaseData = extractPurchaseData(filteredPurchaseTableView.value)
        
        if (purchaseData.length === 0) {
            ElMessage.warning('没有可复制的数据')
            return
        }
        
        // 格式化为制表符分隔的文本（方便粘贴到Excel等）
        const text = purchaseData
            .map(item => `${item.type_name}\t${item.real_quantity}`)
            .join('\n')
        
        // 复制到剪贴板
        await navigator.clipboard.writeText(text)
        ElMessage.success(`已复制 ${purchaseData.length} 条采购清单到剪贴板`)
    } catch (error) {
        console.error('复制失败:', error)
        ElMessage.error('复制失败，请重试')
    }
}


</script>

<template>
    <div class="purchase-view">
        <!-- 左侧或上方采购表 -->
        <!-- 工具栏：分组后「类型」列不再需要，复制入口挪到这里 -->
        <div class="purchase-toolbar">
            <el-button size="small" @click="copyPurchaseList">
                <el-icon><CopyDocument /></el-icon>
                <span>复制清单</span>
            </el-button>
            <div class="purchase-stats">
                <KStat label="全局出单" :value="formatAccounting(jitaSellTotalPrice)" />
                <KStat label="收单" :value="formatAccounting(jitaBuyTotalPrice)" />
                <KStat
                    label="扫单成本"
                    :value="formatAccounting((jitaSellTotalPrice || 0) - (jitaBuyTotalPrice || 0))"
                    tone="primary"
                />
            </div>
        </div>

        <GroupedReportTable
            :groups="groups"
            :table-width="TABLE_WIDTH"
            :sum-props="SUM_PROPS"
            :total-fields="TOTAL_FIELDS"
            :cell-class-name="copyCellClassName"
            row-key="type_id"
        >
        <!-- 单组复制 -->
        <template #group-action="{ group }">
            <el-button text size="small" class="group-copy-btn" @click.stop="copyGroupPurchaseList(group)">
                <el-icon><CopyDocument /></el-icon>
                复制
            </el-button>
        </template>
            <el-table-column label="图标" width="70" fixed="left">
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
            </el-table-column>            <el-table-column label="物品名en" prop="type_name" width="200">
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
            <el-table-column
                label="缺失"
            sortable="custom"
                prop="real_quantity"
                width="150"
           >
                <template #default="{ row }">
                    <div 
                        class="copyable-cell" 
                        @click="copyCellContent(row.real_quantity, '缺失', $event)"
                        :title="`点击复制: ${formatAccounting(row.real_quantity)}`"
                   >
                        {{ formatAccounting(row.real_quantity) }}
                    </div>
                </template>
            </el-table-column><el-table-column label="JITA 出单" width="150" align="right">
                <template #default="{ row }">
                    <div v-if="row.real_quantity> 0">
                        {{ formatAccounting(row.sell_price) }}
                    </div>
                </template>
            </el-table-column>
        <el-table-column label="4H 出单" prop="frt_sell" width="160" align="right" sortable="custom">
            <template #default="{ row }">
                <div v-if="frtSellOf(row)" class="cost-cell"
                    :class="frtDiffOf(row) >= 0 ? 'num-good' : 'num-danger'">
                    <span class="cost-main">{{ formatAccounting(frtSellOf(row)) }}</span>
                    <span class="cost-sub">
                        ({{ frtDiffOf(row) >= 0 ? '+' : '-' }}{{ formatAccounting(Math.abs(frtDiffOf(row))) }})
                    </span>
                </div>
                <span v-else class="num-muted">—</span>
            </template>
        </el-table-column>
            <el-table-column label="JITA 出单 总价" prop="sell_total" width="200" align="right" sortable="custom"
                :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
            <el-table-column label="JITA 收单" width="150" align="right">
                <template #default="{ row }">
                    <div v-if="row.real_quantity> 0">
                        {{ formatAccounting(row.buy_price) }}
                    </div>
                </template>
            </el-table-column>
            <el-table-column label="JITA 收单 总价" prop="buy_total" width="200" align="right" sortable="custom"
                :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
            <el-table-column label="扫单成本增加" prop="diff_total" width="200" align="right" sortable="custom"
                :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        </GroupedReportTable>
        <!-- 右侧或下方类型分布 ecahrts饼图 -->
        <div></div>
    </div>
</template>

<style scoped>
/* 表格吃满 tab 高度，纵向/横向滚动条都留在可视区内 */
.purchase-view {
    height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.purchase-toolbar {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 2px 2px 6px;
}

/* 全局合计：与工具栏同一行、右对齐的指标组（不做成徽章，风格与表头文字一致） */
.purchase-stats {
    display: flex;
    align-items: baseline;
    gap: 22px;
}

/* 可点击复制的单元格样式 */
.copyable-cell {
    cursor: pointer;
    user-select: none;
}


/* 两行单元格：主数值 + 括号差值（正负由外层语义类着色） */
.cost-cell {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    line-height: 1.3;
    font-variant-numeric: tabular-nums;
}

.cost-main {
    font-weight: 600;
}

.cost-sub {
    font-size: var(--k-font-xs);
    opacity: 0.85;
}
</style>
