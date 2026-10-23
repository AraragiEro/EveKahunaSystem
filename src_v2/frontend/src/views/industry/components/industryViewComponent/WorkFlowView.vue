<script setup lang="ts">
/* eslint-disable @typescript-eslint/no-explicit-any -- 工作流数据沿用后端原始结构（历史 any 契约），P2 只做 KTable 替换，未改数据契约 */
import { flashCopied, createCopyCellClassName } from '@/composables/useCopyCell'
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, CircleCheckFilled, CircleClose, Share, Management, Loading, QuestionFilled, Search } from '@element-plus/icons-vue'
import { useWorkflowImplementation, getWorkflowItemKey } from '@/composables/useWorkflowImplementation'
import { useWorkflowImplementationSync } from '@/composables/useWorkflowImplementationSync'
import { useAuthStore } from '@/stores/auth'
import KTable from '@/components/k/KTable.vue'

// Props定义
const props = defineProps<{
    workFlowData: any[]
    selectedPlan: string | null
    // 新增：从父组件接收过滤快照（用于公开页面）
    filterSnapshot?: {
        showFake?: string
        materialUnavailable?: boolean
        activeIdFilter?: string
        classTypeFilter?: string[]
        categoryFilter?: string[]
        marketGroupFilter?: string[]
    }
    // 新增：只读模式
    readonly?: boolean
    // 新增：分享token（用于接取管理）
    shareToken?: string | null
    // 新增：计算周期ID（用于实施标记）
    calculationId?: number | null
}>()

// 获取当前用户
const authStore = useAuthStore()
const userName = computed(() => authStore.user?.username || '')
const planName = computed(() => props.selectedPlan)
const calculationId = computed(() => props.calculationId || null)

// 使用实施标记 composable
const {
    toggleImplemented,
    implementations,
    lastSynced,
    saveLocalState,
    setRunsImplemented,
    getRunsImplemented,
    getRunsImplementedDisplay
} = useWorkflowImplementation(userName, planName, calculationId)

// 使用同步 composable
const {
    isSyncing,
    conflicts,
    isOnline,
    syncNow,
    startAutoSync,
    stopAutoSync,
    fetchFromServer,
    getSyncStatusText,
    hasPendingChanges,
    removeEventListeners
} = useWorkflowImplementationSync(
    userName,
    planName,
    calculationId,
    implementations,
    lastSynced,
    {
        onConflict: (conflictList) => {
            console.log('[WorkFlowView] 冲突:', conflictList)
            // 解决冲突后保存到本地
            saveLocalState()
        },
        onSyncSuccess: () => {
            console.log('[WorkFlowView] 同步成功')
            // 同步成功后保存到本地存储
            saveLocalState()
        }
    }
)

// 部分实施对话框状态
const partialDialogVisible = ref(false)
const partialDialogItem = ref<any>(null)
const partialInputValue = ref(1)

// 定义事件
const emit = defineEmits<{
    share: [filterSnapshot: object]
    'manage-claims': []
}>()

// 过滤器状态 - 如果有快照则使用快照值
const showFake = ref(props.filterSnapshot?.showFake ?? 'all')
const materialUnavailable = ref(props.filterSnapshot?.materialUnavailable ?? false)
const activeIdFilter = ref(props.filterSnapshot?.activeIdFilter ?? 'all')
const classTypeFilter = ref<string[]>(props.filterSnapshot?.classTypeFilter ?? [])
const categoryFilter = ref<string[]>(props.filterSnapshot?.categoryFilter ?? [])
const marketGroupFilter = ref<string[]>(props.filterSnapshot?.marketGroupFilter ?? [])

// 如果传入快照，同步更新过滤器
watch(() => props.filterSnapshot, (newSnapshot) => {
    if (newSnapshot) {
        showFake.value = newSnapshot.showFake ?? 'all'
        materialUnavailable.value = newSnapshot.materialUnavailable ?? false
        activeIdFilter.value = newSnapshot.activeIdFilter ?? 'all'
        classTypeFilter.value = newSnapshot.classTypeFilter ?? []
        categoryFilter.value = newSnapshot.categoryFilter ?? []
        marketGroupFilter.value = newSnapshot.marketGroupFilter ?? []
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
    const secs = Math.round(seconds % 60)
    
    const parts: string[] = []
    if (days > 0) parts.push(`${days}天`)
    if (hours > 0) parts.push(`${hours}小时`)
    if (minutes > 0) parts.push(`${minutes}分钟`)
    if (secs > 0 && days === 0 && hours === 0) parts.push(`${secs}秒`)
    
    return parts.join('') || '0秒'
}

// 获取剩余线数
const remainingRuns = (row: any): number => {
  const key = getWorkflowItemKey({ type_id: row.type_id, runs: row.runs, fake: row.fake, avaliable: row.avaliable })
  return Math.max(0, row.runs_count - (getRunsImplemented(key) || 0))
}

// 安全显示已实施线数（clamp 防溢出）
const displayRuns = (row: any): number => {
  const key = getWorkflowItemKey({ type_id: row.type_id, runs: row.runs, fake: row.fake, avaliable: row.avaliable })
  return getRunsImplementedDisplay(key, row.runs_count)
}

// 进度百分比（0-100整数）
const progressPercent = (row: any): number => {
  return Math.round((displayRuns(row) / row.runs_count) * 100)
}

// 复制单元格内容
// footer 汇总：只合计数量类列
const WORKFLOW_SUM_PROPS = ['runs_count', 'runs']
const summaryMethod = ({ columns, data }: { columns: any[], data: any[] }) => {
    return columns.map((col: any, index: number) => {
        if (index === 0) return '合计'
        const prop = col.property
        if (!prop || !WORKFLOW_SUM_PROPS.includes(prop)) return ''
        const total = (data || []).reduce((s: number, row: any) => s + (Number(row?.[prop]) || 0), 0)
        return formatAccounting(total)
    })
}
// 可复制列标记（复制成功的高亮由 flashCopied 直接加在 td 上）
const copyCellClassName = createCopyCellClassName(['type_name', 'type_name_zh', 'runs_count'])

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

// 从数据中提取可用分类选项
const availableCategories = computed(() => {
    const cats = new Set<string>()
    props.workFlowData.forEach((w: any) => {
        if (w.category_name) cats.add(w.category_name)
    })
    return Array.from(cats).sort()
})

// 从数据中提取可用市场组选项
const availableMarketGroups = computed(() => {
    const mgs = new Set<string>()
    props.workFlowData.forEach((w: any) => {
        (w.market_group_list || []).slice(0, -1).forEach((mg: string) => mgs.add(mg))
    })
    return Array.from(mgs).sort()
})

// 工作流表格数据计算
// 市场组筛选：面板内搜索 + 全选/清空 + 路径提示
const mgSearch = ref('')
const marketGroupPathMap = computed(() => {
    const map = new Map<string, string>()
    props.workFlowData.forEach((w: any) => {
        const path: string[] = w.market_group_list || []
        path.slice(0, -1).forEach((mg: string, i: number) => {
            if (!map.has(mg)) map.set(mg, path.slice(0, i + 1).join(' / '))
        })
    })
    return map
})
const filteredMarketGroups = computed(() => {
    const kw = mgSearch.value.trim().toLowerCase()
    const all = availableMarketGroups.value as string[]
    if (!kw) return all
    return all.filter((mg: string) => {
        const full = marketGroupPathMap.value.get(mg) || mg
        return full.toLowerCase().includes(kw) || mg.toLowerCase().includes(kw)
    })
})
const toggleMarketGroup = (mg: string) => {
    const i = marketGroupFilter.value.indexOf(mg)
    if (i >= 0) marketGroupFilter.value.splice(i, 1)
    else marketGroupFilter.value.push(mg)
}
const selectAllMarketGroups = () => {
    marketGroupFilter.value = [...(filteredMarketGroups.value as string[])]
}
const workFlowTableView = computed(() => {
    // 使用嵌套对象进行分组：type_id -> fake -> avaliable -> runs
    const grouped: Record<string, Record<string, Record<string, Record<string, { count: number, eiv: number, active_time: number }>>>> = {}
    const typeInfo: Record<string, { type_name: string, type_name_zh: string, avaliable: boolean, active_id: number, class_type: string, category_name: string, market_group_list: string[] }> = {}
    
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
                class_type: work.class_type || '其他',
                category_name: work.category_name || '',
                market_group_list: (work.market_group_list || []).slice(0, -1)
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
                    if ((showFake.value === 'no_blueprint' && !fake) || 
                        (showFake.value === 'has_blueprint' && fake) || 
                        (materialUnavailable.value && !avaliable) || 
                        (activeIdFilter.value !== 'all' && info.active_id !== parseInt(activeIdFilter.value)) ||
                        (classTypeFilter.value.length > 0 && !classTypeFilter.value.includes(info.class_type)) ||
                        (categoryFilter.value.length > 0 && !categoryFilter.value.includes(info.category_name)) ||
                        (marketGroupFilter.value.length > 0 && !info.market_group_list.some((mg: string) => marketGroupFilter.value.includes(mg)))) {
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
                        category_name: info.category_name,
                        market_group_list: info.market_group_list,
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


// ============ 分享功能 ============

// 处理分享按钮点击
const handleShare = () => {
    const snapshot = {
        showFake: showFake.value,
        materialUnavailable: materialUnavailable.value,
        activeIdFilter: activeIdFilter.value,
        classTypeFilter: classTypeFilter.value,
        categoryFilter: categoryFilter.value,
        marketGroupFilter: marketGroupFilter.value
    }
    emit('share', snapshot)
}

// 处理接取管理按钮点击
const handleManageClaims = () => {
    emit('manage-claims')
}

// 打开部分实施对话框
const openPartialDialog = (row: any) => {
  partialDialogItem.value = row
  partialInputValue.value = 1
  partialDialogVisible.value = true
}

// 确认部分实施
const confirmPartial = () => {
  if (!partialDialogItem.value) return
  const key = getWorkflowItemKey({
    type_id: partialDialogItem.value.type_id,
    runs: partialDialogItem.value.runs,
    fake: partialDialogItem.value.fake,
    avaliable: partialDialogItem.value.avaliable
  })
  const current = getRunsImplemented(key) || 0
  setRunsImplemented(key, current + partialInputValue.value, partialDialogItem.value.runs_count)
  partialDialogVisible.value = false
  partialDialogItem.value = null
}

// 处理二元切换按钮点击
const handleBinaryToggle = (row: any) => {
  if (isReadonly.value) return
  const key = getWorkflowItemKey({ type_id: row.type_id, runs: row.runs, fake: row.fake, avaliable: row.avaliable })
  const currentRuns = getRunsImplemented(key) || 0
  // 如果部分实施：标记为全量完成
  if (currentRuns > 0 && currentRuns < row.runs_count) {
    setRunsImplemented(key, row.runs_count, row.runs_count)
  } else {
    // 否则：二元切换
    toggleImplemented(key, row.runs_count)
  }
}

// 已实施行背景色样式函数（参考 FlowView.vue 的 CompleteRowClassName）
const ImplementRowClassName = (data: { row: any; rowIndex: number }) => {
    const itemKey = getWorkflowItemKey({
        type_id: data.row.type_id,
        runs: data.row.runs,
        fake: data.row.fake,
        avaliable: data.row.avaliable
    })
    const runs = getRunsImplemented(itemKey) ?? 0
    const total = data.row.runs_count ?? 0
    if (runs >= total && total > 0) return 'implemented-row'
    if (runs > 0 && runs < total) return 'partially-implemented-row'
    return ''
}

// 获取当前过滤快照（供父组件调用）
const getCurrentFilterSnapshot = () => {
    return {
        showFake: showFake.value,
        materialUnavailable: materialUnavailable.value,
        activeIdFilter: activeIdFilter.value,
        classTypeFilter: classTypeFilter.value,
        categoryFilter: categoryFilter.value,
        marketGroupFilter: marketGroupFilter.value
    }
}

// 暴露方法给父组件
defineExpose({
    getCurrentFilterSnapshot
})

// 标记是否已初始化同步
let syncInitialized = false

// 生命周期钩子
onMounted(async () => {
    if (calculationId.value && !isReadonly.value && !syncInitialized) {
        // 先从服务器加载状态
        const loaded = await fetchFromServer()
        if (loaded) {
            // 保存到本地存储
            saveLocalState()
        }
        // 然后启动自动同步（30秒间隔）
        await startAutoSync(30000)
        syncInitialized = true
    }
})

// 监听 calculationId 变化（当计算完成后会赋值）
watch(calculationId, async (newVal, oldVal) => {
    if (newVal && !oldVal && !isReadonly.value && !syncInitialized) {
        console.log(`[WorkFlowView] calculationId 变为有效值: ${newVal}，开始加载服务器状态`)
        // 先从服务器加载状态
        const loaded = await fetchFromServer()
        if (loaded) {
            // 保存到本地存储
            saveLocalState()
        }
        // 然后启动自动同步（30秒间隔）
        await startAutoSync(30000)
        syncInitialized = true
    }
})

onUnmounted(() => {
    // 停止同步并清理事件监听
    stopAutoSync()
    removeEventListeners()
    syncInitialized = false
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
            <!-- 同步状态指示器（仅在有 calculationId 时显示） -->
            <div v-if="calculationId" class="sync-status-wrapper">
                <el-tag 
                    size="small" 
                    :type="isSyncing ? 'warning' : conflicts.length > 0 ? 'danger' : hasPendingChanges() ? 'info' : 'success'"
                    class="sync-status-tag"
                >
                    <el-icon v-if="isSyncing" class="is-loading"><Loading /></el-icon>
                    <el-icon v-else-if="conflicts.length > 0"><CircleCloseFilled /></el-icon>
                    <el-icon v-else-if="!isOnline"><CircleCloseFilled /></el-icon>
                    <el-icon v-else><CircleCheckFilled /></el-icon>
                    <span>{{ getSyncStatusText() }}</span>
                </el-tag>
                <el-button 
                    v-if="!isSyncing && (hasPendingChanges() || conflicts.length > 0)" 
                    link 
                    size="small" 
                    @click="syncNow"
                    class="sync-now-btn"
                >
                    立即同步
                </el-button>
            </div>
        </div>
        
        <!-- 实施标记提示 -->
        <div v-if="!isReadonly && calculationId" class="implementation-hint">
            <el-tag size="small" type="info">
                <el-icon><CircleCheckFilled /></el-icon>
                <span>可勾选"实施状态"列标记已完成的工作</span>
            </el-tag>
        </div>
        
        <KTable :cell-class-name="copyCellClassName"
            :data="workFlowTableView"
            :key="`workflow-table-${selectedPlan || 'default'}`"
            :row-class-name="ImplementRowClassName"


            empty-why="当前计划还没有工作流"
            empty-hint="先在工业计划里添加生产步骤，这里会按物品汇总线数与材料状态"
            show-summary
            :summary-method="summaryMethod"
            height="100%"
        >
        <el-table-column label="icon" width="120">
            <template #default="{ row }">
                <img :src="`https://imageserver.eveonline.com/types/${row.type_id}/icon`" alt="类型" width="40" height="40" loading="lazy" />
            </template>
        </el-table-column>
        <el-table-column label="物品id" prop="type_id" width="100" />
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
        <el-table-column label="物品名zh" prop="type_name_zh" width="200">
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.type_name_zh, '物品名zh', $event)"
                    :title="`点击复制: ${row.type_name_zh || ''}`"
                >
                    {{ row.type_name_zh }}
                </div>
            </template>
        </el-table-column>
        <el-table-column label="线" prop="runs_count" width="120" align="right" sortable="custom" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)">
            <template #header>
                <span>线</span>
            </template>
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.runs_count, 'Runs Count', $event)"
                    :title="`点击复制: ${row.runs_count || ''}`"
                >
                    {{ formatAccounting(row.runs_count) }}
                </div>
            </template>
        </el-table-column>
        <el-table-column label="流程" prop="runs" width="100" align="right" sortable="custom" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)">
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.runs, 'Runs', $event)"
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
        <el-table-column label="分配蓝图" prop="fake" width="125">
            <template #header>
                <span>有蓝图</span>
                <el-select
                    v-model="showFake"
                    :disabled="isReadonly"
                    size="small"
                    style="width: 90px; margin-left: 4px;"
                >
                    <el-option value="all" label="所有" />
                    <el-option value="no_blueprint" label="无蓝图" />
                    <el-option value="has_blueprint" label="有蓝图" />
                </el-select>
            </template>
            <template #default="{ row }">
                <div style="display: flex; align-items: center; justify-content: center;">
                <el-icon v-if="row.fake" size="20" style="color: #f56c6c;"><CircleCloseFilled /></el-icon>
                <el-icon v-else size="20" style="color: #67c23a;"><CircleCheckFilled /></el-icon>
                </div>
            </template>
        </el-table-column>
        <el-table-column label="类型" width="130">
            <template #header>
                <span>类型</span>
                <el-select v-model="categoryFilter" :disabled="isReadonly" multiple collapse-tags collapse-tags-tooltip size="small" style="max-width: 100px;">
                    <el-option v-for="cat in availableCategories" :key="cat" :value="cat" :label="cat" />
                </el-select>
            </template>
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.category_name, '类型', $event)"
                    :title="`点击复制: ${row.category_name || ''}`"
                >
                    {{ row.category_name }}
                </div>
            </template>
        </el-table-column>
        <el-table-column label="市场组" width="100">
            <template #header>
                <el-popover trigger="click" placement="bottom-start" :width="330" popper-class="mg-filter-pop" @show="mgSearch = ''">
                    <template #reference>
                        <button type="button" class="hdr-filter-btn" :class="{ active: marketGroupFilter.length > 0 }"
                            :disabled="isReadonly">
                            <span>市场组</span>
                            <span v-if="marketGroupFilter.length" class="hdr-filter-count">{{ marketGroupFilter.length }}</span>
                            <el-icon class="hdr-filter-caret"><ArrowDown /></el-icon>
                        </button>
                    </template>
                    <div class="mg-filter-panel">
                        <el-input v-model="mgSearch" size="small" placeholder="输入关键字筛选" clearable :prefix-icon="Search" />
                        <div class="mg-filter-tools">
                            <el-button text size="small" @click="selectAllMarketGroups">全选</el-button>
                            <el-button text size="small" @click="marketGroupFilter = []">清空</el-button>
                            <span class="mg-filter-stat">已选 {{ marketGroupFilter.length }} / {{ filteredMarketGroups.length }}</span>
                        </div>
                        <div class="mg-filter-list">
                            <el-checkbox v-for="mg in filteredMarketGroups" :key="mg"
                                :model-value="marketGroupFilter.includes(mg)" @change="toggleMarketGroup(mg)">
                                <span class="mg-filter-item">
                                    <span class="mg-filter-name">{{ mg }}</span>
                                    <span class="mg-filter-path">{{ marketGroupPathMap.get(mg) }}</span>
                                </span>
                            </el-checkbox>
                            <div v-if="!filteredMarketGroups.length" class="mg-filter-empty">没有匹配的市场组</div>
                        </div>
                    </div>
                </el-popover>
            </template>
            <template #default="{ row }">
                <el-popover trigger="hover" placement="top" :width="300" :disabled="!(row.market_group_list || []).length">
                    <template #reference>
                        <div class="market-group-line">
                            {{ (row.market_group_list || []).join(' / ') }}
                        </div>
                    </template>
                    <div class="mg-tooltip-content">
                        <el-tag v-for="mg in row.market_group_list" :key="mg" size="small" type="info" class="mg-tag">
                            {{ mg }}
                        </el-tag>
                    </div>
                </el-popover>
            </template>
        </el-table-column>
        <el-table-column label="活动id" width="100">
            <template #header>
                <el-select v-model="activeIdFilter" :disabled="isReadonly" size="small" class="hdr-filter-select">
                    <el-option value="all" label="工作类型·所有" />
                    <el-option value="1" label="工作类型·制造" />
                    <el-option value="11" label="工作类型·反应" />
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
                    @click="copyCellContent(row.class_type, '产物类型', $event)"
                    :title="`点击复制: ${row.class_type || ''}`"
                >
                    {{ row.class_type }}
                </div>
            </template>
        </el-table-column>
        <el-table-column width="150">
            <template #header>
                <span>EIV</span>
            </template>
            <template #default="{ row }">
                <div 
                    class="copyable-cell" 
                    @click="copyCellContent(row.eiv, 'EIV', $event)"
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
                    @click="copyCellContent(row.active_time, '估计时间', $event)"
                    :title="`点击复制: ${row.active_time || ''}秒`"
                >
                    {{ formatDuration(row.active_time) }}
                </div>
            </template>
        </el-table-column>
        
        <!-- 实施状态列（仅在有 calculationId 且非只读模式时显示） -->
        <el-table-column
          v-if="!isReadonly && calculationId"
          width="200"
          fixed="right"
        >
          <template #header>
            <span>
              实施状态
              <el-tooltip
                content="仅用于标记已进行的工作，对计算无任何影响，重新计算时清空状态。"
                placement="top"
              >
                <el-icon style="margin-left: 4px; cursor: help;">
                  <QuestionFilled />
                </el-icon>
              </el-tooltip>
            </span>
          </template>
          <template #default="{ row }">
            <div class="implementation-cell">
              <!-- 进度条 -->
              <el-progress
                :percentage="progressPercent(row)"
                :status="displayRuns(row) >= row.runs_count ? 'success' : ''"
                :stroke-width="3"
                :show-text="false"
                style="width: 100%"
              />
              <!-- 文本 + 按钮同行 -->
              <div class="implementation-bottom">
                <span class="implementation-progress-text">{{ displayRuns(row) }}/{{ row.runs_count }}线</span>
                <el-button
                  :type="displayRuns(row) >= row.runs_count ? 'success' : 'default'"
                  :plain="displayRuns(row) < row.runs_count"
                  size="small"
                  @click="() => handleBinaryToggle(row)"
                  class="implementation-btn"
                >
                  <el-icon v-if="displayRuns(row) >= row.runs_count"><CircleCheckFilled /></el-icon>
                  <el-icon v-else><CircleClose /></el-icon>
                  <span v-if="displayRuns(row) >= row.runs_count">已实施</span>
                  <span v-else>未实施</span>
                </el-button>
                <template v-if="row.runs_count > 1 && displayRuns(row) < row.runs_count">
                  <el-button
                    v-if="displayRuns(row) > 0"
                    type="warning" size="small" plain
                    @click="openPartialDialog(row)"
                    class="implementation-btn"
                  >追加</el-button>
                  <el-button
                    v-else
                    type="warning" size="small" plain
                    @click="openPartialDialog(row)"
                    class="implementation-btn"
                  >部分</el-button>
                </template>
              </div>
            </div>
          </template>
        </el-table-column>
    </KTable>
    
    <!-- 部分实施对话框 -->
    <el-dialog
      v-model="partialDialogVisible"
      title="输入实施线数"
      width="400px"
      :close-on-click-modal="false"
    >
      <div v-if="partialDialogItem" class="partial-dialog-content">
        <p class="partial-dialog-hint">
          已实施 {{ displayRuns(partialDialogItem) }} / {{ partialDialogItem.runs_count }} 线，
          最多可输入 {{ remainingRuns(partialDialogItem) }} 线
        </p>
        <el-input-number
          v-model="partialInputValue"
          :min="1"
          :max="remainingRuns(partialDialogItem)"
          :step="1"
          size="large"
          style="width: 100%"
        />
      </div>
      <template #footer>
        <el-button @click="partialDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmPartial">确认</el-button>
      </template>
    </el-dialog>
    </div>
</template>

<style scoped>
.workflow-view-container {
    display: flex;
    flex-direction: column;
    gap: 16px;
    height: 100%;
    min-height: 0;
}

.workflow-view-container > :deep(.el-table) {
    flex: 1 1 auto;
    min-height: 0;
}

.workflow-toolbar {
    flex: 0 0 auto;
    display: flex;
    justify-content: flex-end;
    padding: 8px 0;
}

/* 可点击复制的单元格样式 */
.copyable-cell {
    cursor: pointer;
    user-select: none;
}

/* 实施标记提示 */
.implementation-hint {
    display: flex;
    align-items: center;
    padding: 8px 12px;
    background-color: color-mix(in srgb, var(--k-color-primary) 10%, var(--k-color-surface));
    border-radius: 4px;
    border-left: 4px solid var(--k-color-primary);
}

.implementation-hint .el-icon {
    margin-right: 6px;
    color: var(--k-color-success);
}

/* 实施状态列样式 - 紧凑布局 */
.implementation-cell {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 1px;
    padding: 2px 0;
}

.implementation-bottom {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    flex-wrap: nowrap;
}

.implementation-progress-text {
    font-size: 13px;
    color: var(--k-color-text-secondary);
    white-space: nowrap;
    flex-shrink: 0;
}

.implementation-btn {
    font-size: 12px;
    padding: 1px 5px;
    height: 22px;
    flex-shrink: 0;
}

.implementation-btn .el-icon {
    margin-right: 1px;
    font-size: 12px;
}

/* 同步状态指示器 */
.sync-status-wrapper {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
}

.sync-status-tag {
    display: flex;
    align-items: center;
    gap: 4px;
}

.sync-status-tag .el-icon {
    font-size: 12px;
}

.sync-status-tag .is-loading {
    animation: rotating 2s linear infinite;
}

@keyframes rotating {
    from {
        transform: rotate(0deg);
    }
    to {
        transform: rotate(360deg);
    }
}

.sync-now-btn {
    padding: 0 4px;
    font-size: 12px;
}

/* 已实施行样式：token 混合，深浅两套都可读（参考 FlowView.vue 的 complete-row） */
:deep(.el-table__body tr.implemented-row),
:deep(.el-table__body tr.implemented-row > td.el-table__cell),
:deep(.el-table__body tr.implemented-row:hover > td.el-table__cell) {
    background-color: color-mix(in srgb, var(--k-color-success) 22%, var(--k-color-surface));
    font-weight: bold;
    color: var(--k-color-text);
}

/* 部分实施行样式：warning 混合，深浅通用 */
:deep(.el-table__body tr.partially-implemented-row),
:deep(.el-table__body tr.partially-implemented-row > td.el-table__cell),
:deep(.el-table__body tr.partially-implemented-row:hover > td.el-table__cell) {
    background-color: color-mix(in srgb, var(--k-color-warning) 18%, var(--k-color-surface));
    color: var(--k-color-text);
}

/* 深色主题 - 已实施行 */


/* 市场组单行截断 */
.market-group-line {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.mg-tooltip-content {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    max-width: 300px;
}

.mg-tag {
    margin: 1px 0;
}
</style>

<style>
/* 表头筛选：按钮 + 市场组复选面板 ─────────────────────────────────
   面板内容被 teleport 到 body，样式必须写在非 scoped 块里。 */
.hdr-filter-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  padding: 2px 6px;
  border: 1px solid var(--k-color-border-subtle);
  border-radius: var(--k-radius-xs);
  background: var(--k-color-surface);
  color: var(--k-color-text-secondary);
  font-size: var(--k-font-xs);
  line-height: 1.6;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.hdr-filter-btn:hover:not(:disabled) {
  border-color: var(--k-color-primary);
  color: var(--k-color-primary);
}

.hdr-filter-btn.active {
  border-color: var(--k-color-primary);
  color: var(--k-color-primary);
  background: color-mix(in srgb, var(--k-color-primary) 10%, var(--k-color-surface));
}

.hdr-filter-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.hdr-filter-count {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

.hdr-filter-caret {
  font-size: 10px;
  opacity: 0.7;
}

.hdr-filter-select {
  width: 100%;
}

.mg-filter-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mg-filter-tools {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--k-color-border-subtle);
}

.mg-filter-tools .el-button + .el-button {
  margin-left: 0;
}

.mg-filter-stat {
  margin-left: auto;
  font-size: var(--k-font-xs);
  color: var(--k-color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.mg-filter-list {
  display: flex;
  flex-direction: column;
  max-height: 280px;
  overflow-y: auto;
}

.mg-filter-list .el-checkbox {
  height: auto;
  margin-right: 0;
  padding: 4px 0;
}

.mg-filter-list .el-checkbox__label {
  width: 100%;
}

.mg-filter-item {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}

.mg-filter-name {
  font-size: var(--k-font-sm);
  color: var(--k-color-text);
}

.mg-filter-path {
  font-size: var(--k-font-xs);
  color: var(--k-color-text-secondary);
  opacity: 0.7;
}

.mg-filter-empty {
  padding: 12px 0;
  text-align: center;
  font-size: var(--k-font-xs);
  color: var(--k-color-text-secondary);
}</style>
