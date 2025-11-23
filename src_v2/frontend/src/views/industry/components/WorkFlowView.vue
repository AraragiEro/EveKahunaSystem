<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'

// Props定义
const props = defineProps<{
    workFlowData: any[]
    selectedPlan: string | null
}>()

// 过滤器状态
const showFake = ref(false)
const showUnavailable = ref(false)
const activeIdFilter = ref('all')

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

// 工作流表格数据计算
const workFlowTableView = computed(() => {
    // 使用嵌套对象进行分组：type_id -> fake -> avaliable -> runs
    const grouped: Record<string, Record<string, Record<string, Record<string, number>>>> = {}
    const typeInfo: Record<string, { type_name: string, type_name_zh: string, avaliable: boolean, active_id: number }> = {}
    
    // 遍历数据，进行分组统计
    props.workFlowData.forEach((work: any) => {
        const typeId = String(work.type_id)
        const fake = work.bp_object?.fake ?? false
        const fakeKey = String(fake)
        const avaliable = work.avaliable ?? false
        const avaliableKey = String(avaliable)
        const runs = work.runs
        
        if (work.type_id === 11548) {
            console.log(work)
        }
        // 保存 type 信息
        if (!(typeId in typeInfo)) {
            typeInfo[typeId] = {
                type_name: work.type_name || '',
                type_name_zh: work.type_name_zh || '',
                avaliable: work.avaliable,
                active_id: work.active_id
            }
        }
        
        // 初始化分组结构
        if (!(typeId in grouped)) {
            grouped[typeId] = {}
        }
        if (!(fakeKey in grouped[typeId])) {
            grouped[typeId][fakeKey] = {}
        }
        if (!(avaliableKey in grouped[typeId][fakeKey])) {
            grouped[typeId][fakeKey][avaliableKey] = {}
        }
        const runsKey = String(runs)
        if (!(runsKey in grouped[typeId][fakeKey][avaliableKey])) {
            grouped[typeId][fakeKey][avaliableKey][runsKey] = 0
        }
        
        // 统计计数
        grouped[typeId][fakeKey][avaliableKey][runsKey]++
    })
    
    // 扁平化为数组
    const result: any[] = []
    Object.keys(grouped).forEach(typeId => {
        const typeIdNum = parseInt(typeId)
        const info = typeInfo[typeId]
        Object.keys(grouped[typeId]).forEach(fakeKey => {
            const fake = fakeKey === 'true'
            Object.keys(grouped[typeId][fakeKey]).forEach(avaliableKey => {
                const avaliable = avaliableKey === 'true'
                Object.keys(grouped[typeId][fakeKey][avaliableKey]).forEach(runsStr => {
                    const runs = parseInt(runsStr)
                    const runsCount = grouped[typeId][fakeKey][avaliableKey][runsStr]
                    if ((showFake.value && !fake) || (showUnavailable.value && !avaliable) || (activeIdFilter.value !== 'all' && info.active_id !== parseInt(activeIdFilter.value))) {
                        return
                    }
                    result.push({
                        type_id: typeIdNum,
                        type_name: info.type_name,
                        type_name_zh: info.type_name_zh,
                        avaliable: avaliable,
                        active_id: info.active_id,
                        fake: fake,
                        runs: runs,
                        runs_count: runsCount
                    })
                })
            })
        })
    })
    
    return result
})
</script>

<template>
    <el-table
        :data="workFlowTableView"
        :key="`workflow-table-${selectedPlan || 'default'}`"
        border
        max-height="75vh"
        show-overflow-tooltip
    >
        <el-table-column label="物品id" prop="type_id" width="100" />
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
        <el-table-column label="物品名zh" prop="type_name_zh" width="200">
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.type_name_zh, '物品名zh')"
                    :title="`点击复制: ${row.type_name_zh || ''}`"
                >
                    {{ row.type_name_zh }}
                </div>
            </template>
        </el-table-column>
        <el-table-column label="流程" prop="runs" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)">
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.runs, 'Runs')"
                    :title="`点击复制: ${row.runs || ''}`"
                >
                    {{ formatAccounting(row.runs) }}
                </div>
            </template>
        </el-table-column>
        <el-table-column label="线" prop="runs_count" width="120" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)">
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.runs_count, 'Runs Count')"
                    :title="`点击复制: ${row.runs_count || ''}`"
                >
                    {{ formatAccounting(row.runs_count) }}
                </div>
            </template>
        </el-table-column>
        <el-table-column label="活动id" width="100">
            <template #header>
                <span>工作类型</span>
                <el-select v-model="activeIdFilter">
                    <el-option value="all">所有</el-option>
                    <el-option value="1" label="制造">制造</el-option>
                    <el-option value="11" label="反应">反应</el-option>
                </el-select>
            </template>
            <template #default="{ row }">
                <span v-if="row.active_id === 1">制造</span>
                <span v-else-if="row.active_id === 11">反应</span>
                <span v-else>未知</span>
            </template>
        </el-table-column>
        <el-table-column label="材料满足" prop="avaliable" width="75">
            <template #header>
                <span>有材料</span>
                <el-switch
                    v-model="showUnavailable"
                    inline-prompt
                    active-text="有材料"
                    inactive-text="所有"
                />
            </template>
            <template #default="{ row }">
                <div style="display: flex; align-items: center; justify-content: center;">
                <el-icon v-if="row.avaliable" size="20" style="color: #67c23a;"><CircleCheckFilled /></el-icon>
                <el-icon v-else size="20" style="color: #f56c6c;"><CircleCloseFilled /></el-icon>
                <!-- {{ row.avaliable ? '是' : '否' }} -->
                </div>
            </template>
        </el-table-column>
        <el-table-column label="分配蓝图" prop="fake" width="75">
            <template #header>
                <span>有蓝图</span>
                <el-switch
                    v-model="showFake"
                    inline-prompt
                    active-text="没蓝图"
                    inactive-text="所有"
                />
            </template>
            <template #default="{ row }">
                <div style="display: flex; align-items: center; justify-content: center;">
                <el-icon v-if="row.fake" size="20" style="color: #f56c6c;"><CircleCloseFilled /></el-icon>
                <el-icon v-else size="20" style="color: #67c23a;"><CircleCheckFilled /></el-icon>
                </div>
            </template>
        </el-table-column>
    </el-table>
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

