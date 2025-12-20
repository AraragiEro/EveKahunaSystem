<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'

// Props定义
const props = defineProps<{
    flowData: any[]
    selectedPlan: string | null
}>()

// 本地存储键前缀
const FLOW_COLUMNS_STORAGE_KEY_PREFIX = 'flow_columns_'

// 不可隐藏的列（第一列：层）
const fixedColumnIds = ['layer_id']

// 列设置选项（不包含不可隐藏的列）
const columnOptions = [
    { id: 'type_id', label: '物品id' },
    { id: 'type_name', label: '物品名en' },
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

// 列设置对话框相关状态
const columnSettingsDialogVisible = ref(false)
const tempVisibleColumnIds = ref<string[]>([])
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

// 获取当前计划的可见列配置
const visibleColumnIds = computed<string[]>(() => {
    const planName = props.selectedPlan || 'default'
    // 先从内存 map 中获取
    let saved: string[] | null = flowColumnSettingsMap.value[planName] || null
    // 如果内存中没有，尝试从 localStorage 加载
    if (!saved) {
        saved = loadFlowColumnSettings(planName)
    }
    // 如果当前计划还没有专门的列配置，就用默认列（所有可隐藏的列）
    const userSelectedColumns = (saved && saved.length > 0) 
        ? saved.filter(id => columnOptions.some(col => col.id === id))
        : defaultVisibleColumnIds
    // 始终包含不可隐藏的列
    return [...fixedColumnIds, ...userSelectedColumns]
})

// 监听计划切换，自动加载列设置
watch(() => props.selectedPlan, (newPlan) => {
    const planName = newPlan || 'default'
    // 如果内存中没有，从 localStorage 加载
    if (!flowColumnSettingsMap.value[planName]) {
        loadFlowColumnSettings(planName)
    }
}, { immediate: true })

// 打开列设置对话框
const openColumnSettingsDialog = () => {
    const planName = props.selectedPlan || 'default'
    // 先从内存 map 中获取
    let saved: string[] | null = flowColumnSettingsMap.value[planName] || null
    // 如果内存中没有，尝试从 localStorage 加载
    if (!saved) {
        saved = loadFlowColumnSettings(planName)
    }
    // 弹窗里只编辑可隐藏列（去掉不可隐藏的列），并保持用户上一次的选择
    const base = (saved && saved.length > 0) ? saved : defaultVisibleColumnIds
    tempVisibleColumnIds.value = base.filter(id => !fixedColumnIds.includes(id))
    columnSettingsDialogVisible.value = true
}

// 确认列设置
const handleColumnSettingsConfirm = () => {
    const planName = props.selectedPlan || 'default'
    // 用户选择的列（只保存可隐藏的列，不可隐藏的列会自动添加）
    saveFlowColumnSettings(planName, tempVisibleColumnIds.value)
    columnSettingsDialogVisible.value = false
}

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
    return data.row.real_quantity <= 0 ? 'complete-row' : 'full'
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
    <div class="flow-view-container">
        <!-- 工具栏 -->
        <div class="flow-toolbar">
            <el-button @click="openColumnSettingsDialog">
                列筛选
            </el-button>
        </div>
        
        <!-- 表格 -->
        <el-table
            class="flow-data-table"
            :data="flowData"
            :key="`flow-table-${selectedPlan || 'default'}`"
            row-key="row_id"
            expand-on-click-node="false"
            default-expand-all
            fit
            border
            max-height="75vh"
            show-overflow-tooltip
            :row-class-name="CompleteRowClassName"
            style="font-size: 16px;"
        >
        <el-table-column v-if="visibleColumnIds.includes('layer_id')" label="层" prop="layer_id" width="60"/>
        <el-table-column label="图标" prop="type_id" width="70">
            <template #default="{ row }">
                <img 
                    v-if="row?.type_id"
                    :src="`https://imageserver.eveonline.com/types/${row.type_id}/icon`" 
                    alt="类型" 
                    width="30" 
                    height="30"
                    style="border-radius: 4px;" 
                />
            </template>
        </el-table-column>
        <el-table-column v-if="visibleColumnIds.includes('type_id')" label="物品id" prop="type_id" width="90"/>
        <el-table-column v-if="visibleColumnIds.includes('type_name')" label="物品名en" prop="type_name">
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
        <el-table-column v-if="visibleColumnIds.includes('tpye_name_zh')" label="物品名zh" prop="tpye_name_zh">
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
        <el-table-column v-if="visibleColumnIds.includes('quantity')" label="总需求" prop="quantity" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column v-if="visibleColumnIds.includes('real_quantity')" label="缺失" prop="real_quantity" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column v-if="visibleColumnIds.includes('redundant')" label="冗余" prop="redundant" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column v-if="visibleColumnIds.includes('store_quantity')" label="库存" prop="store_quantity" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column v-if="visibleColumnIds.includes('running_jobs')" label="运行中任务" prop="running_jobs"/>
        <el-table-column v-if="visibleColumnIds.includes('real_jobs')" label="缺失流程" prop="real_jobs" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column v-if="visibleColumnIds.includes('jobs')" label="总流程" prop="jobs" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column v-if="visibleColumnIds.includes('bp_quantity')" label="蓝图库存单位" prop="bp_quantity" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
        <el-table-column v-if="visibleColumnIds.includes('bp_jobs')" label="蓝图库存流程" prop="bp_jobs">
            <template #default="{ row }">
                <template v-if="row?.bp_jobs">
                    <span v-if="Number(row?.bp_jobs?.bpc) > 0">
                        {{ Number(row?.bp_jobs?.bpc) }} 流程拷贝
                    </span>
                    <span v-if="Number(row?.bp_jobs?.bpc) > 0 && Number(row?.bp_jobs?.bpo) > 0">，</span>
                    <span v-if="Number(row?.bp_jobs?.bpo) > 0">
                        {{ Number(row?.bp_jobs?.bpo) }} 份原图
                    </span>
                </template>
            </template>
        </el-table-column>
        <el-table-column v-if="visibleColumnIds.includes('status')" label="状态" prop="status" />
    </el-table>

    <!-- 列设置对话框 -->
    <el-dialog
        v-model="columnSettingsDialogVisible"
        title="列显示设置"
        width="400px"
        :close-on-click-modal="false"
    >
        <p style="margin-bottom: 10px;">勾选需要显示的列（"层"列始终显示，不可关闭）</p>
        <el-checkbox-group v-model="tempVisibleColumnIds">
            <el-checkbox
                v-for="col in columnOptions"
                :key="col.id"
                :label="col.id"
            >
                {{ col.label }}
            </el-checkbox>
        </el-checkbox-group>
        <template #footer>
            <el-button @click="columnSettingsDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="handleColumnSettingsConfirm">确定</el-button>
        </template>
    </el-dialog>
    </div>
</template>

<style scoped>
.flow-view-container {
    display: flex;
    flex-direction: column;
    height: 100%;
}

.flow-toolbar {
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 10px;
}

:deep(.el-table__body tr.complete-row) {
    background-color: #e7ffc8 !important;
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

