<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import { http } from '@/http'
import type { PlanProductTableData, PlanTableData } from './components/interfaceType.vue'
import { ElMessage } from 'element-plus'
import { Document, Loading, Check, Close, Refresh, CopyDocument } from '@element-plus/icons-vue'

// localStorage key 前缀
const STORAGE_KEY_PREFIX = 'plan_calculate_result_'
const SELECTED_PLAN_KEY = 'flow_decomposition_selected_plan'

// 拉取计划列表
const selectedPlan = ref<string | null>(null)
const planList = ref<PlanTableData[]>([])
const getPlanList = async () => {
    const res = await http.post('/EVE/industry/getPlanTableData')
    const data = await res.json()
    planList.value = data.data
    
    // 如果计划列表加载完成，尝试恢复之前选择的计划
    if (planList.value.length > 0 && !selectedPlan.value) {
        restoreSelectedPlan()
    }
}

// 保存选中的计划到本地
const saveSelectedPlan = (planName: string | null) => {
    try {
        if (planName) {
            localStorage.setItem(SELECTED_PLAN_KEY, planName)
        } else {
            localStorage.removeItem(SELECTED_PLAN_KEY)
        }
    } catch (error) {
        console.error('保存选中计划失败:', error)
    }
}

// 从本地恢复选中的计划
const restoreSelectedPlan = () => {
    try {
        const savedPlan = localStorage.getItem(SELECTED_PLAN_KEY)
        if (savedPlan && planList.value.length > 0) {
            // 检查保存的计划是否还在计划列表中
            const planExists = planList.value.some(plan => plan.plan_name === savedPlan)
            if (planExists) {
                selectedPlan.value = savedPlan
                console.log(`恢复选中的计划: ${savedPlan}`)
            } else {
                // 如果计划不存在，清除保存的状态
                localStorage.removeItem(SELECTED_PLAN_KEY)
                console.log(`保存的计划 ${savedPlan} 已不存在，已清除`)
            }
        }
    } catch (error) {
        console.error('恢复选中计划失败:', error)
    }
}

// 保存计算结果到本地
const saveToLocal = (planName: string, data: any, keys: string) => {
    try {
        const key = `${STORAGE_KEY_PREFIX}${keys}${planName}`
        localStorage.setItem(key, JSON.stringify(data))
        console.log(`计算结果已保存到本地: ${planName}`)
    } catch (error) {
        console.error('保存到本地失败:', error)
    }
}

// 从本地读取计算结果
const loadFromLocal = (planName: string, keys: string): any[] | null => {
    try {
        const key = `${STORAGE_KEY_PREFIX}${keys}${planName}`
        const data = localStorage.getItem(key)
        if (data) {
            const parsed = JSON.parse(data)
            console.log(`从本地加载计算结果: ${planName}`)
            return parsed
        }
    } catch (error) {
        console.error('从本地读取失败:', error)
    }
    return null
}

// 拉取计划计算结果
const PlanCalculateMaterialTableView = ref<any[]>([])
const PlanCalculateResultTableView = ref<any[]>([])
const PlanCalculateWorkFlowTableView = ref<any[]>([])

// 计算状态管理
const isCalculating = ref<boolean>(false)
const calculationStatus = ref<string>('idle') // idle, pending, running, completed, failed
const calculationProgress = ref<number>(0) // 总进度
const currentStepName = ref<string>('') // 当前步骤名称
const currentStepProgress = ref<number>(0) // 当前步骤进度
const currentStepProgressIndeterminate = ref<boolean>(false) // 当前步骤进度是否不确定
const calculationError = ref<string | null>(null)

// 定时器
let statusPollingInterval: number | null = null

// 启动计算
const getPlanCalculateResultTableViewStart = async () => {
    console.log("getPlanCalculateResultTableViewStart", selectedPlan.value)
    if (!selectedPlan.value) {
        ElMessage.error("请选择计划")
        return
    }
    try {
        const res = await http.post('/EVE/industry/getPlanCalculateResultTableView',
            {
                plan_name: selectedPlan.value,
                operate_type: "start"
            }
        )
        
        // 检查 HTTP 响应状态
        if (!res.ok) {
            ElMessage.error(`请求失败: HTTP ${res.status}`)
            return
        }
        
        const data = await res.json()
        
        if (data.status !== 200) {
            ElMessage.error(data.error || "启动计算失败")
            return
        }
        
        // 设置计算状态
        isCalculating.value = true
        calculationStatus.value = 'pending'
        calculationProgress.value = 0
        currentStepName.value = ''
        currentStepProgress.value = 0
        calculationError.value = null
        
        // 启动状态轮询
        startStatusPolling()
        
        ElMessage.success("计算任务已启动")
    } catch (error) {
        console.error("getPlanCalculateResultTableViewStart error:", error)
        ElMessage.error(error instanceof Error ? error.message : "网络请求失败，请稍后重试")
    }
}

// 查询计算状态
const getPlanCalculateResultTableViewStatus = async (showCompletedMessage: boolean = true) => {
    if (!selectedPlan.value) {
        return
    }
    try {
        const res = await http.post('/EVE/industry/getPlanCalculateResultTableView',
            {
                plan_name: selectedPlan.value,
                operate_type: "status"
            }
        )
        
        if (!res.ok) {
            return
        }
        
        const data = await res.json()
        
        if (data.status !== 200) {
            return
        }
        
        const statusData = data.data || {}
        calculationStatus.value = statusData.status || 'idle'
        calculationProgress.value = statusData.total_progress || 0
        
        // 更新当前步骤信息
        if (statusData.current_step) {
            currentStepName.value = statusData.current_step.name || ''
            currentStepProgress.value = statusData.current_step.progress || 0
            currentStepProgressIndeterminate.value = statusData.current_step.is_indeterminate || false
        } else {
            currentStepName.value = ''
            currentStepProgress.value = 0
            currentStepProgressIndeterminate.value = false
        }
        
        // 如果状态为失败，显示错误信息
        if (statusData.status === 'failed') {
            calculationError.value = statusData.error || '计算失败'
            isCalculating.value = false
            stopStatusPolling()
            ElMessage.error(calculationError.value || '计算失败')
        }
        // 如果状态为完成，自动获取结果
        else if (statusData.status === 'completed') {
            isCalculating.value = false
            stopStatusPolling()
            // 只有在轮询过程中检测到完成时才显示消息，页面重新加载时不显示
            await getPlanCalculateResultTableViewResult(showCompletedMessage)
        }
        // 如果状态为运行中，更新进度
        else if (statusData.status === 'running') {
            // 进度已在上面更新
        }
    } catch (error) {
        console.error("getPlanCalculateResultTableViewStatus error:", error)
        // 网络错误时不显示错误，避免频繁报错
    }
}

// 获取计算结果
const getPlanCalculateResultTableViewResult = async (showMessage: boolean = true) => {
    if (!selectedPlan.value) {
        return
    }
    try {
        const res = await http.post('/EVE/industry/getPlanCalculateResultTableView',
            {
                plan_name: selectedPlan.value,
                operate_type: "result"
            }
        )
        
        // 检查 HTTP 响应状态
        if (!res.ok) {
            ElMessage.error(`请求失败: HTTP ${res.status}`)
            return
        }
        
        const data = await res.json()
        
        if (data.status !== 200) {
            ElMessage.error(data.error || "获取数据失败")
            return
        }
        
        // 先清空数据，避免数据错位
        PlanCalculateResultTableView.value = []
        PlanCalculateMaterialTableView.value = []
        const resultData = data.data || {}
        // 使用 nextTick 确保 DOM 更新完成后再赋值，避免数据错位
        await nextTick()
        PlanCalculateResultTableView.value = resultData.flow_output || []
        PlanCalculateMaterialTableView.value = resultData.material_output || []
        PlanCalculateWorkFlowTableView.value = resultData.work_flow || []
        
        // 保存到本地
        saveToLocal(selectedPlan.value, resultData.flow_output, "flow")
        saveToLocal(selectedPlan.value, resultData.material_output, "material")
        saveToLocal(selectedPlan.value, resultData.work_flow, "work_flow")

        calculationStatus.value = 'completed'
        // 只有在需要时才显示成功消息（轮询检测到完成时显示，页面重新加载时不显示）
        if (showMessage) {
            ElMessage.success("计算成功")
        }
    } catch (error) {
        console.error("getPlanCalculateResultTableViewResult error:", error)
        ElMessage.error(error instanceof Error ? error.message : "网络请求失败，请稍后重试")
    }
}

// 启动状态轮询
const startStatusPolling = () => {
    // 如果已有定时器，先清除
    if (statusPollingInterval !== null) {
        clearInterval(statusPollingInterval)
    }
    
    // 立即查询一次状态
    getPlanCalculateResultTableViewStatus()
    
    // 每2秒轮询一次状态
    statusPollingInterval = window.setInterval(() => {
        getPlanCalculateResultTableViewStatus()
    }, 2000)
}

// 停止状态轮询
const stopStatusPolling = () => {
    if (statusPollingInterval !== null) {
        clearInterval(statusPollingInterval)
        statusPollingInterval = null
    }
}

// 监听计划选择变化，自动加载本地数据
watch(selectedPlan, (newPlan) => {
    // 保存选中的计划到本地
    saveSelectedPlan(newPlan)
    
    // 停止之前的轮询
    stopStatusPolling()
    isCalculating.value = false
    calculationStatus.value = 'idle'
    calculationProgress.value = 0
    currentStepName.value = ''
    currentStepProgress.value = 0
    calculationError.value = null
    
    if (newPlan) {
        const localDataFlow = loadFromLocal(newPlan, "flow")
        const localDataMaterial = loadFromLocal(newPlan, "material")
        const localDataWorkFlow = loadFromLocal(newPlan, "work_flow")
        if (localDataFlow) {
            PlanCalculateResultTableView.value = localDataFlow
        } else {
            PlanCalculateResultTableView.value = []
        }
        if (localDataMaterial) {
            PlanCalculateMaterialTableView.value = localDataMaterial
        } else {
            PlanCalculateMaterialTableView.value = []
        }
        if (localDataWorkFlow) {
            PlanCalculateWorkFlowTableView.value = localDataWorkFlow
        } else {
            PlanCalculateWorkFlowTableView.value = []
        }
        // 检查是否有正在进行的计算
        checkCalculationStatus()
    } else {
        PlanCalculateResultTableView.value = []
        PlanCalculateMaterialTableView.value = []
        PlanCalculateWorkFlowTableView.value = []
    }
})

// 检查计算状态（用于页面刷新后恢复状态）
const checkCalculationStatus = async () => {
    if (!selectedPlan.value) {
        return
    }
    try {
        // 页面重新加载时检查状态，不显示完成消息（避免重复提示）
        await getPlanCalculateResultTableViewStatus(false)
        // 如果状态为pending或running，启动轮询
        if (calculationStatus.value === 'pending' || calculationStatus.value === 'running') {
            isCalculating.value = true
            startStatusPolling()
        }
    } catch (error) {
        console.error("checkCalculationStatus error:", error)
    }
}

onMounted(async () => {
    // 加载计划列表（加载完成后会自动恢复选中的计划）
    await getPlanList()
    
    // 计划列表加载完成后，如果有选中的计划，尝试从本地加载数据
    if (selectedPlan.value) {
        const localData = loadFromLocal(selectedPlan.value, "flow")
        const localDataMaterial = loadFromLocal(selectedPlan.value, "material")
        const localDataWorkFlow = loadFromLocal(selectedPlan.value, "work_flow")
        if (localData) {
            PlanCalculateResultTableView.value = localData
        }
        if (localDataMaterial) {
            PlanCalculateMaterialTableView.value = localDataMaterial
        }
        if (localDataWorkFlow) {
            PlanCalculateWorkFlowTableView.value = localDataWorkFlow
        } else {
            PlanCalculateWorkFlowTableView.value = []
        }
        // 检查是否有正在进行的计算
        checkCalculationStatus()
    }
})

onUnmounted(() => {
    // 清理定时器
    stopStatusPolling()
})

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

const lackRowClassName = (data: { row: any, rowIndex: number }) => {
    return data.row.real_quantity > 0 ? 'lack-row' : 'full'
}

const showFake = ref(false)
const showUnavailable = ref(false)
const workFlowTableView = computed(() => {
    // 使用嵌套对象进行分组：type_id -> fake -> runs
    const grouped: Record<string, Record<string, Record<string, number>>> = {}
    const typeInfo: Record<string, { type_name: string, type_name_zh: string, avaliable: boolean }> = {}
    
    // 遍历数据，进行分组统计
    PlanCalculateWorkFlowTableView.value.forEach((work: any) => {
        const typeId = String(work.type_id)
        const fake = work.bp_object?.fake ?? false
        const fakeKey = String(fake)
        const runs = work.runs
        
        // 保存 type 信息
        if (!(typeId in typeInfo)) {
            typeInfo[typeId] = {
                type_name: work.type_name || '',
                type_name_zh: work.type_name_zh || '',
                avaliable: work.avaliable
            }
        }
        
        // 初始化分组结构
        if (!(typeId in grouped)) {
            grouped[typeId] = {}
        }
        if (!(fakeKey in grouped[typeId])) {
            grouped[typeId][fakeKey] = {}
        }
        const runsKey = String(runs)
        if (!(runsKey in grouped[typeId][fakeKey])) {
            grouped[typeId][fakeKey][runsKey] = 0
        }
        
        // 统计计数
        grouped[typeId][fakeKey][runsKey]++
    })
    
    // 扁平化为数组
    const result: any[] = []
    Object.keys(grouped).forEach(typeId => {
        const typeIdNum = parseInt(typeId)
        const info = typeInfo[typeId]
        Object.keys(grouped[typeId]).forEach(fakeKey => {
            const fake = fakeKey === 'true'
            Object.keys(grouped[typeId][fakeKey]).forEach(runsStr => {
                const runs = parseInt(runsStr)
                const runsCount = grouped[typeId][fakeKey][runsStr]
                if ((showFake.value && !fake) || (showUnavailable.value && !info.avaliable)) {
                    return
                }
                result.push({
                    type_id: typeIdNum,
                    type_name: info.type_name,
                    type_name_zh: info.type_name_zh,
                    avaliable: info.avaliable,
                    fake: fake,
                    runs: runs,
                    runs_count: runsCount
                })
            })
        })
    })
    
    return result
})

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
    return filterTreeByRealQuantity(PlanCalculateMaterialTableView.value)
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

</script>

<template>
<div style="max-height: 50vh;">
    <div class="control-panel">
        <el-card shadow="never" class="control-card">
            <el-row :gutter="20" align="middle">
                <!-- 计划选择区域 -->
                <el-col :span="6">
                    <div class="control-item">
                        <div class="control-label">
                            <el-icon class="label-icon"><Document /></el-icon>
                            <span>选择计划</span>
                        </div>
                        <el-select
                            v-model="selectedPlan"
                            :options="planList"
                            :props="{value:'plan_name', label:'plan_name'}"
                            placeholder="请选择计划"
                            style="width: 100%"
                            clearable
                        />
                    </div>
                </el-col>
                
                <!-- 操作按钮区域 -->
                <el-col :span="4">
                    <div class="control-item">
                        <el-button 
                            type="primary" 
                            :icon="calculationStatus === 'running' ? Loading : Refresh"
                            :loading="calculationStatus === 'running' || calculationStatus === 'pending'"
                            @click="getPlanCalculateResultTableViewStart"
                            :disabled="!selectedPlan || calculationStatus === 'running' || calculationStatus === 'pending'"
                            style="width: 100%"
                        >
                            {{ calculationStatus === 'running' || calculationStatus === 'pending' ? '计算中...' : '立刻计算' }}
                        </el-button>
                    </div>
                </el-col>
                
                <!-- 进度显示区域 -->
                <el-col :span="14">
                    <div class="progress-container">
                        <!-- 总进度 -->
                        <div class="progress-item">
                            <div class="progress-header">
                                <div class="progress-label">
                                    <el-icon 
                                        class="status-icon"
                                        :class="{
                                            'icon-idle': calculationStatus === 'idle',
                                            'icon-pending': calculationStatus === 'pending',
                                            'icon-running': calculationStatus === 'running',
                                            'icon-success': calculationStatus === 'completed',
                                            'icon-error': calculationStatus === 'failed'
                                        }"
                                    >
                                        <Loading v-if="calculationStatus === 'pending' || calculationStatus === 'running'" />
                                        <Check v-else-if="calculationStatus === 'completed'" />
                                        <Close v-else-if="calculationStatus === 'failed'" />
                                        <Document v-else />
                                    </el-icon>
                                    <span class="label-text">总进度</span>
                                </div>
                                <span class="progress-text">
                                    <template v-if="calculationStatus === 'idle'">未开始</template>
                                    <template v-else-if="calculationStatus === 'pending'">等待中...</template>
                                    <template v-else-if="calculationStatus === 'running'">{{ calculationProgress }}%</template>
                                    <template v-else-if="calculationStatus === 'completed'">计算完成</template>
                                    <template v-else-if="calculationStatus === 'failed'">计算失败</template>
                                </span>
                            </div>
                            <el-progress 
                                :percentage="calculationProgress" 
                                :status="calculationStatus === 'completed' ? 'success' : calculationStatus === 'failed' ? 'exception' : undefined"
                                :stroke-width="12"
                                :show-text="false"
                                class="progress-bar"
                                striped
                                striped-flow
                                :duration="calculationStatus === 'running' ? 20 : 100"
                                color=#409EFF
                            />
                        </div>
                        
                        <!-- 当前步骤进度 -->
                        <div v-if="calculationStatus === 'running' && currentStepName" class="progress-item step-progress">
                            <div class="progress-header">
                                <div class="progress-label">
                                    <el-icon class="status-icon icon-running"><Loading /></el-icon>
                                    <span class="label-text">当前步骤</span>
                                </div>
                                <span class="progress-text">{{ currentStepProgress }}%</span>
                            </div>
                            <el-progress 
                                :percentage="currentStepProgress" 
                                :stroke-width="10"
                                :show-text="false"
                                color="#409EFF"
                                class="progress-bar"
                                :indeterminate="currentStepProgressIndeterminate"
                                striped
                                striped-flow
                                :duration="3"
                                
                            />
                            <div class="step-name">{{ currentStepName }}</div>
                        </div>
                        
                        <!-- 错误信息 -->
                        <div v-if="calculationStatus === 'failed' && calculationError" class="error-message">
                            <el-icon><Close /></el-icon>
                            <span>{{ calculationError }}</span>
                        </div>
                    </div>
                </el-col>
            </el-row>
        </el-card>
    </div>
    <div>
        <el-row>
        <el-tabs style="width: 100%;">
            <el-tab-pane label="流程视图">
                <el-table
                    :data="PlanCalculateResultTableView"
                    :key="`flow-table-${selectedPlan || 'default'}`"
                    row-key="type_id"
                    expand-on-click-node="false"
                    default-expand-all
                    fit
                    border
                    max-height="75vh"
                    show-overflow-tooltip
                    :row-class-name="lackRowClassName"
                >
                    <el-table-column label="层" prop="layer_id" width="60"/>
                    <el-table-column label="物品id" prop="type_id" width="70"/>
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
                    <el-table-column label="总需求" prop="quantity" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                    <el-table-column label="缺失" prop="real_quantity" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                    <el-table-column label="冗余" prop="redundant" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                    <el-table-column label="库存" prop="store_quantity" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                    <el-table-column label="运行中任务" prop="running_jobs"/>
                    <el-table-column label="缺失流程" prop="real_jobs" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                    <el-table-column label="总流程" prop="jobs" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                    <el-table-column label="蓝图库存单位" prop="bp_quantity" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                    <el-table-column label="蓝图库存流程" prop="bp_jobs" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                    <el-table-column label="状态" prop="status" />

                </el-table>
            </el-tab-pane>
            <el-tab-pane label="材料视图">
                <el-table
                    :data="PlanCalculateMaterialTableView"
                    :key="`material-table-${selectedPlan || 'default'}`"
                    row-key="type_id"
                    expand-on-click-node="false"
                    default-expand-all
                    border
                    max-height="75vh"
                    show-overflow-tooltip
                    :row-class-name="lackRowClassName"
                >
                    <el-table-column label="类型" prop="layer_id" />
                    <el-table-column label="物品id" prop="type_id" />
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
                    <el-table-column label="缺失" prop="real_quantity" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                    <el-table-column label="总需求" prop="quantity" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                    <el-table-column label="库存" prop="store_quantity" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
            </el-table>
            </el-tab-pane>
            
            <!-- 工作流视图 -->
            <el-tab-pane label="工作流">
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
                    <el-table-column label="材料满足" prop="avaliable" width="150">
                        <template #header>
                            <el-switch
                                v-model="showUnavailable"
                                inline-prompt
                                active-text="显示可进行工作"
                                inactive-text="隐藏所有工作"
                            />
                        </template>
                        <template #default="{ row }">
                            {{ row.avaliable ? '是' : '否' }}
                        </template>
                    </el-table-column>
                    <el-table-column label="分配蓝图" prop="fake" width="150">
                        <template #header>
                            <el-switch
                                v-model="showFake"
                                inline-prompt
                                active-text="蓝图缺失"
                                inactive-text="显示所有工作"
                            />
                        </template>
                        <template #default="{ row }">
                            {{ row.fake ? '是' : '否' }}
                        </template>
                    </el-table-column>
                    <el-table-column label="Runs" prop="runs" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)">
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
                    <el-table-column label="Runs Count" prop="runs_count" width="120" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)">
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
            </el-table>
            </el-tab-pane>

            <!-- 采购视图 -->
            <el-tab-pane label="采购视图">
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
                        <el-table-column
                            label="采购价格"
                            prop="purchase_price"
                            :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"
                        />
                    </el-table>
                    <!-- 右侧或下方类型分布 ecahrts饼图 -->
                    <div></div>
                </div>
            </el-tab-pane>
        </el-tabs>
        </el-row>
    </div>
</div>
</template>

<style scoped>
:deep(.el-table .lack-row) {
    background-color: #ff7979 !important;
    font-weight: bold !important;
    color: #000000 !important;
}

.control-panel {
    margin-bottom: 20px;
}

.control-card {
    border-radius: 8px;
    border: 1px solid #e4e7ed;
}

.control-item {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.control-label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
    font-weight: 500;
    color: #606266;
}

.label-icon {
    font-size: 16px;
    color: #409eff;
}

.progress-container {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.progress-item {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.progress-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.progress-label {
    display: flex;
    align-items: center;
    gap: 8px;
}

.label-text {
    font-size: 14px;
    font-weight: 500;
    color: #606266;
}

.status-icon {
    font-size: 16px;
    animation: none;
}

.status-icon.icon-idle {
    color: #909399;
}

.status-icon.icon-pending {
    color: #e6a23c;
    animation: rotate 2s linear infinite;
}

.status-icon.icon-running {
    color: #409eff;
    animation: rotate 2s linear infinite;
}

.status-icon.icon-success {
    color: #67c23a;
}

.status-icon.icon-error {
    color: #f56c6c;
}

@keyframes rotate {
    from {
        transform: rotate(0deg);
    }
    to {
        transform: rotate(360deg);
    }
}

.progress-text {
    font-size: 13px;
    font-weight: 600;
    color: #303133;
    min-width: 60px;
    text-align: right;
}

.progress-bar {
    flex: 1;
}

.step-progress {
    padding-top: 8px;
    border-top: 1px solid #f0f2f5;
}

.step-name {
    font-size: 12px;
    color: #909399;
    margin-top: 4px;
    padding-left: 24px;
}

.error-message {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 12px;
    background-color: #fef0f0;
    border: 1px solid #fde2e2;
    border-radius: 4px;
    color: #f56c6c;
    font-size: 13px;
}

.error-message .el-icon {
    font-size: 14px;
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

/* 响应式设计 */
@media (max-width: 1200px) {
    .control-card :deep(.el-col) {
        margin-bottom: 16px;
    }
}
</style>