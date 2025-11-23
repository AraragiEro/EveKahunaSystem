<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument } from '@element-plus/icons-vue'

// Props定义
const props = defineProps<{
    materialData: any[]
    selectedPlan: string | null
}>()

// 递归过滤树结构，只保留 real_quantity > 0 的节点
const filterTreeByRealQuantity = (nodes: any[]): any[] => {
    return nodes.map((node: any) => {
        // 如果有 children，递归过滤子节点
        if (node.children && Array.isArray(node.children) && node.children.length > 0) {
            const filteredChildren = filterTreeByRealQuantity(node.children)
            // 如果过滤后还有子节点，保留该节点（但只保留过滤后的子节点）
            if (filteredChildren.length > 0) {
                return {
                    ...node,
                    children: filteredChildren
                }
            }
        }
        // 检查节点本身的 real_quantity（可能是叶子节点，或者顶层节点本身也有 real_quantity）
        if (node.real_quantity !== undefined && node.real_quantity > 0) {
            return node
        }
        // 不满足条件，返回 null（后续会被过滤掉）
        return null
    }).filter((node: any) => node !== null) // 过滤掉 null 值
}

// 采购视图过滤后的数据（只显示 real_quantity > 0 的行，保持树结构）
const filteredPurchaseTableView = computed(() => {
    return filterTreeByRealQuantity(props.materialData)
})

// 递归提取树结构中的物品名和缺失数量
const extractPurchaseData = (nodes: any[]): Array<{ type_name: string, real_quantity: number }> => {
    const result: Array<{ type_name: string, real_quantity: number }> = []
    
    nodes.forEach((node: any) => {
        // 如果有 children，递归处理子节点
        if (node.children && Array.isArray(node.children) && node.children.length > 0) {
            result.push(...extractPurchaseData(node.children))
        }
        // 如果是叶子节点且有 real_quantity，添加到结果中
        if (node.type_name && node.real_quantity !== undefined && node.real_quantity > 0) {
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
const copyCellContent = async (content: string | number | null | undefined, fieldName: string = '') => {
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
    <div>
        <!-- 左侧或上方采购表 -->
        <el-table
            :data="filteredPurchaseTableView"
            :key="`purchase-table-${selectedPlan || 'default'}`"
            row-key="type_id"
            expand-on-click-node="false"
            default-expand-all
            border
            max-height="75vh"
            show-overflow-tooltip
        >
            <el-table-column label="类型" prop="layer_id" width="120">
                <template #header>
                    <el-button size="small" @click="copyPurchaseList">
                        <el-icon><CopyDocument /></el-icon>
                        <span>复制清单</span>
                    </el-button>
                </template>
            </el-table-column>
            <el-table-column label="物品名en" prop="type_name">
                <template #default="{ row }">
                    <div 
                        class="copyable-cell" 
                        @click="copyCellContent(row.type_name, '物品名en')"
                        :title="`点击复制: ${row.type_name || ''}`"
                    >
                        {{ row.type_name }}
                    </div>
                </template>
            </el-table-column>
            <el-table-column label="物品名zh" prop="tpye_name_zh">
                <template #default="{ row }">
                    <div 
                        class="copyable-cell" 
                        @click="copyCellContent(row.tpye_name_zh, '物品名zh')"
                        :title="`点击复制: ${row.tpye_name_zh || ''}`"
                    >
                        {{ row.tpye_name_zh }}
                    </div>
                </template>
            </el-table-column>
            <el-table-column
                label="缺失"
                prop="real_quantity"
            >
                <template #default="{ row }">
                    <div 
                        class="copyable-cell" 
                        @click="copyCellContent(row.real_quantity, '缺失')"
                        :title="`点击复制: ${formatAccounting(row.real_quantity)}`"
                    >
                        {{ formatAccounting(row.real_quantity) }}
                    </div>
                </template>
            </el-table-column>
            <el-table-column label="JITA 出单">
                <template #default="{ row }">
                    <div v-if="row.real_quantity > 0">
                        {{ formatAccounting(row.sell_price) }}
                    </div>
                </template>
            </el-table-column>
            <el-table-column label="JITA 出单 总价">
                <template #default="{ row }">
                    <div v-if="row.real_quantity > 0">
                        {{ formatAccounting(row.sell_price * row.real_quantity) }}
                    </div>
                </template>
            </el-table-column>
            <el-table-column label="JITA 收单">
                <template #default="{ row }">
                    <div v-if="row.real_quantity > 0">
                        {{ formatAccounting(row.buy_price) }}
                    </div>
                </template>
            </el-table-column>
            <el-table-column label="JITA 收单 总价">
                <template #default="{ row }">
                    <div v-if="row.real_quantity > 0">
                        {{ formatAccounting(row.buy_price * row.real_quantity) }}
                    </div>
                </template>
            </el-table-column>
            <el-table-column label="扫单成本增加">
                <template #default="{ row }">
                    <div v-if="row.real_quantity > 0">
                        {{ formatAccounting(row.sell_price * row.real_quantity - row.buy_price * row.real_quantity) }}
                    </div>
                </template>
            </el-table-column>
        </el-table>
        <!-- 右侧或下方类型分布 ecahrts饼图 -->
        <div></div>
    </div>
</template>

<style scoped>
/* 可点击复制的单元格样式 */
.copyable-cell {
    cursor: pointer;
    user-select: none;
    padding: 4px 8px;
    margin: -4px -8px;
    border-radius: 4px;
    transition: all 0.2s;
}

.copyable-cell:hover {
    background-color: #f0f9ff;
    color: #409eff;
}

.copyable-cell:active {
    background-color: #e1f5ff;
    transform: scale(0.98);
}
</style>

