<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled, CircleCloseFilled, Share, Management } from '@element-plus/icons-vue'

// Props定义
const props = defineProps<{
    workFlowData: any[]
    selectedPlan: string | null
    // 新增：从父组件接收过滤快照（用于公开页面）
    filterSnapshot?: {
        showFake?: boolean
        materialUnavailable?: boolean
        activeIdFilter?: string
        classTypeFilter?: string[]
    }
    // 新增：只读模式
    readonly?: boolean
    // 新增：分享token（用于接取管理）
    shareToken?: string | null
}>()

// 定义事件
const emit = defineEmits<{
    share: [filterSnapshot: object]
    'manage-claims': []
}>()

// 过滤器状态 - 如果有快照则使用快照值
const showFake = ref(props.filterSnapshot?.showFake ?? false)
const materialUnavailable = ref(props.filterSnapshot?.materialUnavailable ?? false)
const activeIdFilter = ref(props.filterSnapshot?.activeIdFilter ?? 'all')
const classTypeFilter = ref<string[]>(props.filterSnapshot?.classTypeFilter ?? [])

// 如果传入快照，同步更新过滤器
watch(() => props.filterSnapshot, (newSnapshot) => {
    if (newSnapshot) {
        showFake.value = newSnapshot.showFake ?? false
        materialUnavailable.value = newSnapshot.materialUnavailable ?? false
        activeIdFilter.value = newSnapshot.activeIdFilter ?? 'all'
        classTypeFilter.value = newSnapshot.classTypeFilter ?? []
    }
}, { deep: true, immediate: true })

// 是否只读模式
const isReadonly = computed(() => props.readonly ?? false)

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

// 时间格式化函数
const formatDuration = (seconds: number): string => {
    if (!seconds || seconds <= 0) return '0秒'
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = seconds % 60
    
    const parts: string[] = []
    if (days > 0) parts.push(`${days}天`)
    if (hours > 0) parts.push(`${hours}小时`)
    if (minutes > 0) parts.push(`${minutes}分钟`)
    if (secs > 0 && days === 0 && hours === 0) parts.push(`${secs}秒`)
    
    return parts.join('') || '0秒'
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
    const grouped: Record<string, Record<string, Record<string, Record<string, { count: number, eiv: number, active_time: number }>>>> = {}
    const typeInfo: Record<string, { type_name: string, type_name_zh: string, avaliable: boolean, active_id: number, class_type: string }> = {}
    
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
                active_id: work.active_id,
                class_type: work.class_type || '其他'
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
            grouped[typeId][fakeKey][avaliableKey][runsKey] = {
                count: 0,
                eiv: 0,
                active_time: work.active_time * (work.time_eff || 1) || 0
            }
        }
        
        // 统计计数和累加eiv
        grouped[typeId][fakeKey][avaliableKey][runsKey].count++
        grouped[typeId][fakeKey][avaliableKey][runsKey].eiv += (work.eiv || 0)
    })
    
    // 扁平化为数组
    const result: any[] = []
    Object.keys(grouped).forEach(typeId => {
        const typeIdNum = parseInt(typeId)
        const info = typeInfo[typeId]
        Object.keys(grouped[typeId]).forEach(fakeKey => {
            const fake = fakeKey === 'true'
            Object.keys(grouped[typeId][fakeKey]).forEach(avaliableKey => {
                // 材料是否满足
                const avaliable = avaliableKey === 'true'
                Object.keys(grouped[typeId][fakeKey][avaliableKey]).forEach(runsStr => {
                    const runs = parseInt(runsStr)
                    const groupData = grouped[typeId][fakeKey][avaliableKey][runsStr]
                    const runsCount = groupData.count
                    if ((showFake.value && !fake) || 
                        (materialUnavailable.value && !avaliable) || 
                        (activeIdFilter.value !== 'all' && info.active_id !== parseInt(activeIdFilter.value)) ||
                        (classTypeFilter.value.length > 0 && !classTypeFilter.value.includes(info.class_type))) {
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
                        runs_count: runsCount,
                        class_type: info.class_type,
                        eiv: groupData.eiv,
                        active_time: groupData.active_time,
                        total_active_time: groupData.active_time * runsCount
                    })
                })
            })
        })
    })
    
    return result
})

// 计算当前筛选结果下的线总计
const totalRunsCount = computed(() => {
    return workFlowTableView.value.reduce((sum, row) => sum + (Number(row.runs_count) || 0), 0)
})

// 计算总EIV
const totalEIV = computed(() => {
    return workFlowTableView.value.reduce((sum, row) => sum + (row.eiv || 0), 0)
})

// ============ 分享功能 ============

// 处理分享按钮点击
const handleShare = () => {
    const snapshot = {
        showFake: showFake.value,
        materialUnavailable: materialUnavailable.value,
        activeIdFilter: activeIdFilter.value,
        classTypeFilter: classTypeFilter.value
    }
    emit('share', snapshot)
}

// 处理接取管理按钮点击
const handleManageClaims = () => {
    emit('manage-claims')
}

// 获取当前过滤快照（供父组件调用）
const getCurrentFilterSnapshot = () => {
    return {
        showFake: showFake.value,
        materialUnavailable: materialUnavailable.value,
        activeIdFilter: activeIdFilter.value,
        classTypeFilter: classTypeFilter.value
    }
}

// 暴露方法给父组件
defineExpose({
    getCurrentFilterSnapshot
})
</script>

<template>
    <div class="workflow-view-container">
        <!-- 工具栏 -->
        <div v-if="!isReadonly" class="workflow-toolbar">
            <el-button
                type="success"
                :icon="Management"
                @click="handleManageClaims"
            >
                接取管理
            </el-button>
            <el-button 
                type="primary" 
                :icon="Share" 
                @click="handleShare"
            >
                分享当前过滤
            </el-button>
        </div>
        
        <el-table
            :data="workFlowTableView"
            :key="`workflow-table-${selectedPlan || 'default'}`"
            border
            max-height="75vh"
            show-overflow-tooltip
        >
        <el-table-column label="icon" width="120">
            <template #default="{ row }">
                <img :src="`https://imageserver.eveonline.com/types/${row.type_id}/icon`" alt="类型" width="40" height="40" />
            </template>
        </el-table-column>
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
        <el-table-column prop="runs_count" width="120" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)">
            <template #header>
                <span>线 (总计: {{ formatAccounting(totalRunsCount) }})</span>
            </template>
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
        <el-table-column label="材料满足" prop="avaliable" width="75">
            <template #header>
                <span>有材料</span>
                <el-switch
                    v-model="materialUnavailable"
                    :disabled="isReadonly"
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
                    :disabled="isReadonly"
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
        <el-table-column label="活动id" width="100">
            <template #header>
                <span>工作类型</span>
                <el-select v-model="activeIdFilter" :disabled="isReadonly">
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
        <el-table-column label="产物类型" width="150">
            <template #header>
                <span>产物类型</span>
                <el-select v-model="classTypeFilter" :disabled="isReadonly" multiple collapse-tags collapse-tags-tooltip>
                    <el-option value="低反">低反</el-option>
                    <el-option value="高反">高反</el-option>
                    <el-option value="分子熔铸">分子熔铸</el-option>
                    <el-option value="聚合物">聚合物</el-option>
                    <el-option value="高级组件">高级组件</el-option>
                    <el-option value="旗舰组件">旗舰组件</el-option>
                    <el-option value="其他">其他</el-option>
                </el-select>
            </template>
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.class_type, '产物类型')"
                    :title="`点击复制: ${row.class_type || ''}`"
                >
                    {{ row.class_type }}
                </div>
            </template>
        </el-table-column>
        <el-table-column width="150">
            <template #header>
                <span>EIV (总计: {{ formatAccounting(totalEIV) }})</span>
            </template>
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.eiv, 'EIV')"
                    :title="`点击复制: ${row.eiv || ''}`"
                >
                    {{ formatAccounting(row.eiv) }}
                </div>
            </template>
        </el-table-column>
        <el-table-column label="估计时间" width="150">
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.active_time, '估计时间')"
                    :title="`点击复制: ${row.active_time || ''}秒`"
                >
                    {{ formatDuration(row.active_time) }}
                </div>
            </template>
        </el-table-column>
    </el-table>
    </div>
</template>

<style scoped>
.workflow-view-container {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.workflow-toolbar {
    display: flex;
    justify-content: flex-end;
    padding: 8px 0;
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

