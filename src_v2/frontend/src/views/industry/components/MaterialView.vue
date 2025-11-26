<script setup lang="ts">
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
const LackRowClassName = (data: { row: any, rowIndex: number }) => {
    return data.row.real_quantity > 0 ? 'lack-row' : 'full'
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
        
        // 优先使用 Clipboard API（需要 HTTPS 或 localhost）
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text)
            ElMessage.success(`已复制${fieldName ? ` ${fieldName} ` : ' '}到剪贴板`)
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
    <el-table
        :data="materialData"
        :key="`material-table-${selectedPlan || 'default'}`"
        row-key="type_id"
        expand-on-click-node="false"
        default-expand-all
        border
        max-height="75vh"
        show-overflow-tooltip
        :row-class-name="LackRowClassName"
        style="font-size: 16px;"
    >
        <el-table-column label="类型" prop="layer_id" width="110">
            <template #default="{ row }">
                <img 
                    v-if="row?.type_id"
                    :src="`https://imageserver.eveonline.com/types/${row.type_id}/icon`" 
                    alt="类型" 
                    width="40" 
                    height="40" 
                />
            </template>
        </el-table-column>
        <el-table-column label="物品id" prop="type_id" width="90"/>
        <el-table-column label="物品名en" prop="type_name" width="200">
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
        <el-table-column label="物品名zh" prop="tpye_name_zh" width="200">
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
        <el-table-column label="缺失" prop="real_quantity" width="150" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column label="总需求" prop="quantity" width="150" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column label="库存" prop="store_quantity" width="150" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
    </el-table>
</template>

<style scoped>
:deep(.el-table .lack-row) {
    background-color: #ffc6c6 !important;
    font-weight: bold !important;
    color: #000000 !important;
}

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

