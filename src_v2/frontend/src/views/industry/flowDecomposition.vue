<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import { http } from '@/http'
import type { PlanProductTableData, PlanTableData } from './components/interfaceType.vue'
import { ElMessage } from 'element-plus'
import { Document, Loading, Check, Close, Refresh } from '@element-plus/icons-vue'
import LaborView from './components/industryViewComponent/LaborView.vue'
import CostView from './components/industryViewComponent/costView.vue'
import PurchaseView from './components/industryViewComponent/PurchaseView.vue'
import WorkFlowView from './components/industryViewComponent/WorkFlowView.vue'
import MaterialView from './components/industryViewComponent/MaterialView.vue'
import FlowView from './components/industryViewComponent/FlowView.vue'
import LogisticsView from './components/industryViewComponent/LogisticsView.vue'
import CompressedAsteroidView from './components/industryViewComponent/compressedAsteroidView.vue'
import { useAuthStore } from '@/stores/auth'
import LZString from 'lz-string'
import WorkflowShareDialog from '@/components/WorkflowShareDialog.vue'
import WorkflowClaimManageDialog from '@/components/WorkflowClaimManageDialog.vue'

const authStore = useAuthStore()
const haveAlphaRole = computed(() => {
    return authStore.user?.roles.includes('vip_alpha') || false
})
const haveAdminRole = computed(() => {
    return authStore.user?.roles.includes('admin') || false
})

// localStorage key 前缀
const STORAGE_KEY_PREFIX = 'plan_calculate_result_'
const SELECTED_PLAN_KEY = 'flow_decomposition_selected_plan'

// 拉取计划列表
const selectedPlan = ref<string | null>(null)
const planList = ref<PlanTableData[]>([])
const getPlanList = async () => {
    const res = await http.post('/EVE/industry/getPlanTableData')
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message || '获取计划列表失败')
        return
    }
    // 如果是管理员模式，为每个计划添加 plan_key 和 plan_display_name
    if (haveAdminRole.value) {
        planList.value = data.data.map((plan: PlanTableData) => ({
            ...plan,
            plan_key: `${plan.user_name}:${plan.plan_name}`,
            plan_display_name: `${plan.user_name}:${plan.plan_name}`
        }))
    } else {
        planList.value = data.data
    }
    
    // 如果计划列表加载完成，尝试恢复之前选择的计划
    if (planList.value.length > 0 && !selectedPlan.value) {
        restoreSelectedPlan()
    }
}

// 获取当前选中计划的完整信息（包含user_name）
const getSelectedPlanInfo = () => {
    if (!selectedPlan.value) return null
    
    // 如果是管理员模式，selectedPlan 是 plan_key 格式 "user_name:plan_name"
    if (haveAdminRole.value) {
        // 从 planList 中查找匹配的计划
        const plan = planList.value.find((p: any) => {
            const key = p.plan_key || `${p.user_name}:${p.plan_name}`
            return key === selectedPlan.value
        })
        if (plan) {
            return { user_name: plan.user_name, plan_name: plan.plan_name }
        }
        // 如果找不到，尝试直接解析 selectedPlan（向后兼容）
        if (selectedPlan.value.includes(':')) {
            const [user_name, plan_name] = selectedPlan.value.split(':', 2)
            return { user_name, plan_name }
        }
    }
    
    // 普通模式，只有 plan_name
    const plan = planList.value.find(p => p.plan_name === selectedPlan.value)
    return plan ? { user_name: plan.user_name, plan_name: plan.plan_name } : null
}

// 保存选中的计划到本地
const saveSelectedPlan = (planValue: string | null) => {
    try {
        if (planValue) {
            localStorage.setItem(SELECTED_PLAN_KEY, planValue)
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
            let planExists = false
            if (haveAdminRole.value) {
                // 管理员模式：查找 plan_key 匹配的计划
                planExists = planList.value.some(plan => {
                    const planKey = (plan as any).plan_key || `${plan.user_name}:${plan.plan_name}`
                    return planKey === savedPlan
                })
            } else {
                // 普通模式：只有 plan_name
                planExists = planList.value.some(plan => plan.plan_name === savedPlan)
            }
            
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

// 清理旧的存储数据（当存储空间不足时）
const cleanupOldStorage = () => {
    try {
        const keys: string[] = []
        // 收集所有相关的存储键
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i)
            if (key && key.startsWith(STORAGE_KEY_PREFIX)) {
                keys.push(key)
            }
        }
        
        // 按时间戳排序（如果有的话），或者简单地删除最旧的一半
        // 这里我们删除除了当前计划之外的所有数据
        const currentPlanKeys = keys.filter(key => {
            // 保留当前选中计划的数据
            if (selectedPlan.value) {
                return key.includes(selectedPlan.value)
            }
            return false
        })
        
        // 删除其他计划的数据
        keys.forEach(key => {
            if (!currentPlanKeys.includes(key)) {
                localStorage.removeItem(key)
            }
        })
        
        console.log('已清理旧的存储数据')
    } catch (error) {
        console.error('清理存储数据失败:', error)
    }
}

// 保存计算结果到本地（带压缩）
const saveToLocal = (planName: string, data: any, keys: string) => {
    try {
        const key = `${STORAGE_KEY_PREFIX}${keys}${planName}`
        const jsonString = JSON.stringify(data)
        
        // 尝试压缩数据
        const compressed = LZString.compress(jsonString)
        
        // 如果压缩后仍然太大（超过 4MB），尝试清理旧数据
        if (compressed && compressed.length > 4 * 1024 * 1024) {
            console.warn('压缩后的数据仍然很大，尝试清理旧数据')
            cleanupOldStorage()
        }
        
        // 尝试保存压缩后的数据
        if (compressed) {
            try {
                localStorage.setItem(key, compressed)
                // 添加标记表示这是压缩数据
                localStorage.setItem(`${key}_compressed`, 'true')
                console.log(`计算结果已保存到本地（已压缩）: ${planName}, 原始大小: ${(jsonString.length / 1024).toFixed(2)}KB, 压缩后: ${(compressed.length / 1024).toFixed(2)}KB`)
            } catch (error) {
                // 如果压缩后仍然太大，尝试清理旧数据后重试
                if (error instanceof DOMException && error.name === 'QuotaExceededError') {
                    console.warn('存储空间不足，清理旧数据后重试')
                    cleanupOldStorage()
                    try {
                        localStorage.setItem(key, compressed)
                        localStorage.setItem(`${key}_compressed`, 'true')
                        console.log(`清理后成功保存: ${planName}`)
                    } catch (retryError) {
                        console.error('清理后仍然无法保存:', retryError)
                        ElMessage.warning('数据量过大，无法保存到本地存储。部分数据可能无法离线访问。')
                    }
                } else {
                    throw error
                }
            }
        } else {
            // 压缩失败，尝试保存原始数据
            try {
                localStorage.setItem(key, jsonString)
                localStorage.removeItem(`${key}_compressed`)
                console.log(`计算结果已保存到本地（未压缩）: ${planName}`)
            } catch (error) {
                if (error instanceof DOMException && error.name === 'QuotaExceededError') {
                    cleanupOldStorage()
                    try {
                        localStorage.setItem(key, jsonString)
                        localStorage.removeItem(`${key}_compressed`)
                        console.log(`清理后成功保存（未压缩）: ${planName}`)
                    } catch (retryError) {
                        console.error('清理后仍然无法保存:', retryError)
                        ElMessage.warning('数据量过大，无法保存到本地存储。部分数据可能无法离线访问。')
                    }
                } else {
                    throw error
                }
            }
        }
    } catch (error) {
        console.error('保存到本地失败:', error)
        if (error instanceof DOMException && error.name === 'QuotaExceededError') {
            ElMessage.warning('本地存储空间不足，无法保存数据。请清理浏览器缓存或使用其他浏览器。')
        }
    }
}

// 从本地读取计算结果（支持解压）
const loadFromLocal = (planName: string, keys: string): any[] | null => {
    try {
        const key = `${STORAGE_KEY_PREFIX}${keys}${planName}`
        const compressedFlag = localStorage.getItem(`${key}_compressed`)
        const data = localStorage.getItem(key)
        
        if (data) {
            let parsed: any
            if (compressedFlag === 'true') {
                // 数据是压缩的，需要解压
                const decompressed = LZString.decompress(data)
                if (decompressed) {
                    parsed = JSON.parse(decompressed)
                } else {
                    console.error('解压数据失败')
                    return null
                }
            } else {
                // 数据未压缩，直接解析
                parsed = JSON.parse(data)
            }
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
const PlanCalculateRunningJobTableView = ref<any[]>([])
const PlanCalculateEIVCostTableView = ref<any[]>([])
const PlanCalculateLogisticsTableView = ref<any[]>([])

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

// ============ 分享功能 ============
const workFlowViewRef = ref<InstanceType<typeof WorkFlowView> | null>(null)
const shareDialogVisible = ref(false)
const currentFilterSnapshot = ref({})
const currentShareToken = ref<string | null>(null)

// 处理分享按钮点击
const handleShareWorkflow = () => {
    // 获取当前过滤快照
    if (workFlowViewRef.value) {
        currentFilterSnapshot.value = workFlowViewRef.value.getCurrentFilterSnapshot()
    }
    shareDialogVisible.value = true
}

// 分享创建成功回调
const handleShareCreated = (shareData: { shareToken: string; shareUrl: string }) => {
    console.log('分享链接已创建:', shareData)
    currentShareToken.value = shareData.shareToken
}

// shareToken 更新回调
const handleShareTokenUpdated = (shareToken: string | null) => {
    console.log('分享Token已更新:', shareToken)
    currentShareToken.value = shareToken
}

// ============ 接取管理功能 ============
const claimManageDialogVisible = ref(false)

// 获取分享状态（用于接取管理）
const fetchShareStatusForClaims = async () => {
    if (!selectedPlan.value) {
        ElMessage.warning('请先选择一个计划')
        return null
    }

    try {
        const planInfo = getSelectedPlanInfo()
        const planName = planInfo ? planInfo.plan_name : selectedPlan.value
        const res = await http.get(`/public/workflow/share/status?plan_name=${encodeURIComponent(planName)}`)
        const data = await res.json()

        if (data.status === 200 && data.data.share_token) {
            currentShareToken.value = data.data.share_token
            return data.data.share_token
        }
        return null
    } catch (error) {
        console.error('获取分享状态失败:', error)
        return null
    }
}

// 处理接取管理按钮点击
const handleManageClaims = async () => {
    // 如果没有 shareToken，先获取
    if (!currentShareToken.value) {
        ElMessage.info('正在获取分享信息...')
        await fetchShareStatusForClaims()
    }
    claimManageDialogVisible.value = true
}

// 启动计算
const getPlanCalculateResultTableViewStart = async () => {
    console.log("getPlanCalculateResultTableViewStart", selectedPlan.value)
    if (!selectedPlan.value) {
        ElMessage.error("请选择计划")
        return
    }
    try {
        const planInfo = getSelectedPlanInfo()
        if (!planInfo) {
            ElMessage.error("无法获取计划信息")
            return
        }
        
        const requestData: any = {
            plan_name: planInfo.plan_name,
            operate_type: "start"
        }
        // 如果是管理员模式且计划属于其他用户，传递 user_name
        if (haveAdminRole.value && planInfo.user_name !== authStore.user?.username) {
            requestData.user_name = planInfo.user_name
        }
        
        const res = await http.post('/EVE/industry/getPlanCalculateResultTableView', requestData)
        
        // 检查 HTTP 响应状态
        if (!res.ok) {
            try {
                const errorData = await res.json()
                ElMessage.error(errorData.message || `请求失败: HTTP ${res.status}`)
            } catch {
                ElMessage.error(`请求失败: HTTP ${res.status}`)
            }
            return
        }
        
        const data = await res.json()
        
        if (data.status !== 200) {
            ElMessage.error(data.message || "启动计算失败")
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
        const planInfo = getSelectedPlanInfo()
        if (!planInfo) {
            return
        }
        
        const requestData: any = {
            plan_name: planInfo.plan_name,
            operate_type: "status"
        }
        // 如果是管理员模式且计划属于其他用户，传递 user_name
        if (haveAdminRole.value && planInfo.user_name !== authStore.user?.username) {
            requestData.user_name = planInfo.user_name
        }
        
        const res = await http.post('/EVE/industry/getPlanCalculateResultTableView', requestData)
        
        if (!res.ok) {
            // 如果有后端返回的message，显示它；否则静默失败（避免轮询时频繁报错）
            try {
                const errorData = await res.json()
                if (errorData.message) {
                    ElMessage.error(errorData.message)
                }
            } catch {
                // 无法解析响应体，静默失败
            }
            return
        }
        
        const data = await res.json()
        
        if (data.status !== 200) {
            // 如果有后端返回的message，显示它；否则静默失败（避免轮询时频繁报错）
            if (data.message) {
                ElMessage.error(data.message)
            }
            return
        }
        
        const statusData = data.data || {}
        calculationStatus.value = statusData.status || 'idle'
        calculationProgress.value = statusData.total_progress || 0
        
        // 更新当前步骤信息
        if (statusData.current_step) {
            currentStepName.value = statusData.current_step.name || ''
            currentStepProgress.value = statusData.current_step.progress || 0
            // 处理 is_indeterminate：支持布尔值、字符串 '1'/'0'、字符串 'true'/'false'
            const isIndeterminate = statusData.current_step.is_indeterminate
            currentStepProgressIndeterminate.value = isIndeterminate === true || 
                isIndeterminate === '1' || 
                isIndeterminate === 'true' || 
                isIndeterminate === 1
        } else {
            currentStepName.value = ''
            currentStepProgress.value = 0
            currentStepProgressIndeterminate.value = true
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
        const planInfo = getSelectedPlanInfo()
        if (!planInfo) {
            return
        }
        
        const requestData: any = {
            plan_name: planInfo.plan_name,
            operate_type: "result"
        }
        // 如果是管理员模式且计划属于其他用户，传递 user_name
        if (haveAdminRole.value && planInfo.user_name !== authStore.user?.username) {
            requestData.user_name = planInfo.user_name
        }
        
        const res = await http.post('/EVE/industry/getPlanCalculateResultTableView', requestData)
        
        // 检查 HTTP 响应状态
        if (!res.ok) {
            try {
                const errorData = await res.json()
                ElMessage.error(errorData.message || `请求失败: HTTP ${res.status}`)
            } catch {
                ElMessage.error(`请求失败: HTTP ${res.status}`)
            }
            return
        }
        
        const data = await res.json()
        
        if (data.status !== 200) {
            ElMessage.error(data.message || "获取数据失败")
            return
        }
        
        // 先清空数据，避免数据错位
        PlanCalculateResultTableView.value = []
        PlanCalculateMaterialTableView.value = []
        PlanCalculateWorkFlowTableView.value = []
        PlanCalculateRunningJobTableView.value = []
        PlanCalculateEIVCostTableView.value = []
        PlanCalculateLogisticsTableView.value = []
        const resultData = data.data || {}
        // 使用 nextTick 确保 DOM 更新完成后再赋值，避免数据错位
        await nextTick()
        PlanCalculateResultTableView.value = resultData.flow_output || []
        PlanCalculateMaterialTableView.value = resultData.material_output || []
        PlanCalculateWorkFlowTableView.value = resultData.work_flow || []
        PlanCalculateRunningJobTableView.value = resultData.running_job_tableview_data || []
        PlanCalculateEIVCostTableView.value = resultData.eiv_cost_dict || []
        PlanCalculateLogisticsTableView.value = resultData.logistic_dict || []
        // 保存到本地
        saveToLocal(selectedPlan.value, resultData.flow_output, "flow")
        saveToLocal(selectedPlan.value, resultData.material_output, "material")
        saveToLocal(selectedPlan.value, resultData.work_flow, "work_flow")
        saveToLocal(selectedPlan.value, resultData.running_job_tableview_data, "running_job")
        saveToLocal(selectedPlan.value, resultData.eiv_cost_dict, "eiv_cost")
        saveToLocal(selectedPlan.value, resultData.logistic_dict, "logistic")
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
        const localDataEIVCost = loadFromLocal(newPlan, "eiv_cost")
        const localDataRunningJob = loadFromLocal(newPlan, "running_job")
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
        if (localDataEIVCost) {
            PlanCalculateEIVCostTableView.value = localDataEIVCost
        } else {
            PlanCalculateEIVCostTableView.value = []
        }
        if (localDataRunningJob) {
            PlanCalculateRunningJobTableView.value = localDataRunningJob
        } else {
            PlanCalculateRunningJobTableView.value = []
        }
        // 检查是否有正在进行的计算
        checkCalculationStatus()
    } else {
        PlanCalculateResultTableView.value = []
        PlanCalculateMaterialTableView.value = []
        PlanCalculateWorkFlowTableView.value = []
        PlanCalculateRunningJobTableView.value = []
        PlanCalculateEIVCostTableView.value = []
        PlanCalculateLogisticsTableView.value = []
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
        const localDataEIVCost = loadFromLocal(selectedPlan.value, "eiv_cost")
        const localDataRunningJob = loadFromLocal(selectedPlan.value, "running_job")
        const localDataLogistics = loadFromLocal(selectedPlan.value, "logistic")
        if (localData) {
            PlanCalculateResultTableView.value = localData
        }
        if (localDataMaterial) {
            PlanCalculateMaterialTableView.value = localDataMaterial
        }
        if (localDataWorkFlow) {
            PlanCalculateWorkFlowTableView.value = localDataWorkFlow
        }
        if (localDataEIVCost) {
            PlanCalculateEIVCostTableView.value = localDataEIVCost
        }
        if (localDataRunningJob) {
            PlanCalculateRunningJobTableView.value = localDataRunningJob
        }
        if (localDataLogistics) {
            PlanCalculateLogisticsTableView.value = localDataLogistics
        }
        // 检查是否有正在进行的计算
        checkCalculationStatus()
    }
})

onUnmounted(() => {
    // 清理定时器
    stopStatusPolling()
})

const LackRowClassName = (data: { row: any, rowIndex: number }) => {
    return data.row.real_quantity > 0 ? 'lack-row' : 'full'
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
                            :props="haveAdminRole ? {value: 'plan_key', label: 'plan_display_name'} : {value:'plan_name', label:'plan_name'}"
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
                                <span class="progress-text">
                                    <template v-if="currentStepProgressIndeterminate">进行中...</template>
                                    <template v-else>{{ currentStepProgress }}%</template>
                                </span>
                            </div>
                            <el-progress 
                                :percentage="currentStepProgressIndeterminate ? 50 : currentStepProgress" 
                                :stroke-width="10"
                                :show-text="false"
                                color="#409EFF"
                                class="progress-bar"
                                :indeterminate="currentStepProgressIndeterminate"
                                :striped="!currentStepProgressIndeterminate"
                                :striped-flow="!currentStepProgressIndeterminate"
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
                <FlowView 
                    :flow-data="PlanCalculateResultTableView"
                    :selected-plan="selectedPlan"
                />
            </el-tab-pane>
            
            <el-tab-pane label="材料视图">
                <MaterialView 
                    :material-data="PlanCalculateMaterialTableView"
                    :selected-plan="selectedPlan"
                />
            </el-tab-pane>
            
            <!-- 工作流视图 -->
            <el-tab-pane label="工作流">
                <WorkFlowView
                    ref="workFlowViewRef"
                    :work-flow-data="PlanCalculateWorkFlowTableView"
                    :selected-plan="selectedPlan"
                    @share="handleShareWorkflow"
                    @manage-claims="handleManageClaims"
                />
            </el-tab-pane>

            <!-- 采购视图 -->
            <el-tab-pane label="采购视图">
                <PurchaseView 
                    :material-data="PlanCalculateMaterialTableView"
                    :selected-plan="selectedPlan"
                />
            </el-tab-pane>
            
            <el-tab-pane label="成本视图" :disabled="!haveAlphaRole">
                <CostView 
                    :-plan-calculate-e-i-v-cost-table-view="PlanCalculateEIVCostTableView"
                />
            </el-tab-pane>
            
            <el-tab-pane label="劳动力视图" :disabled="!haveAlphaRole">
                <LaborView :running-jobs="PlanCalculateRunningJobTableView" />
            </el-tab-pane>

            <el-tab-pane label="物流视图" :disabled="!haveAlphaRole">
                <LogisticsView 
                    :logistics-data="PlanCalculateLogisticsTableView"
                    :selected-plan="selectedPlan"
                />
            </el-tab-pane>

            <el-tab-pane label="化矿求解视图" :disabled="!haveAlphaRole">
                <CompressedAsteroidView 
                    :material-data="PlanCalculateMaterialTableView"
                    :selected-plan="selectedPlan"
                />
            </el-tab-pane>

        </el-tabs>
        </el-row>
    </div>
    
    <!-- 分享对话框 -->
    <WorkflowShareDialog
        v-model="shareDialogVisible"
        :plan-name="selectedPlan || ''"
        :filter-snapshot="currentFilterSnapshot"
        @share-created="handleShareCreated"
        @share-token-updated="handleShareTokenUpdated"
    />
    
    <!-- 接取管理对话框 -->
    <WorkflowClaimManageDialog
        v-model="claimManageDialogVisible"
        :plan-name="selectedPlan || ''"
        :share-token="currentShareToken"
    />
</div>
</template>

<style scoped>
/* 浅色主题：缺失材料行使用较深的红色背景 */
:deep(.el-table .lack-row) {
    background-color: #ff6b6b !important;
    font-weight: bold !important;
    color: #ffffff !important;
}

/* 深色主题：缺失材料行使用亮红色背景 */
.dark :deep(.el-table .lack-row),
[data-theme="dark"] :deep(.el-table .lack-row),
html.dark :deep(.el-table .lack-row) {
    background-color: #ff4444 !important;
    font-weight: bold !important;
    color: #ffffff !important;
}

/* 完成任务的行样式 */
:deep(.el-table .complete-job) {
    background-color: #e7ffc8 !important;
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

/* 响应式设计 */
@media (max-width: 1200px) {
    .control-card :deep(.el-col) {
        margin-bottom: 16px;
    }
}

/* Theme override */
.control-card,
.control-item,
.progress-container,
.progress-item,
.step-progress {
    background: var(--k-color-surface) !important;
    border-color: var(--k-color-border) !important;
    color: var(--k-color-text) !important;
}

.control-label,
.label-text,
.step-name {
    color: var(--k-color-text-secondary) !important;
}

.progress-text {
    color: var(--k-color-text) !important;
}

:deep(.el-tabs__item) {
    color: var(--k-color-text-secondary) !important;
}

:deep(.el-tabs__item.is-active) {
    color: var(--k-color-primary) !important;
}

:deep(.el-tabs--card > .el-tabs__header .el-tabs__item),
:deep(.el-tabs--border-card > .el-tabs__header .el-tabs__item) {
    background: var(--k-color-surface) !important;
    border-color: var(--k-color-border) !important;
    color: var(--k-color-text-secondary) !important;
}

:deep(.el-tabs--card > .el-tabs__header .el-tabs__item.is-active),
:deep(.el-tabs--border-card > .el-tabs__header .el-tabs__item.is-active) {
    color: var(--k-color-primary) !important;
    background: color-mix(in srgb, var(--k-color-primary) 8%, var(--k-color-surface-soft)) !important;
}

:deep(.el-tabs__content),
:deep(.el-card),
:deep(.el-card__header),
:deep(.el-card__body),
:deep(.el-input__wrapper),
:deep(.el-select__wrapper),
:deep(.el-input-number .el-input__wrapper),
:deep(.el-input-number__decrease),
:deep(.el-input-number__increase),
:deep(.el-table),
:deep(.el-table th.el-table__cell),
:deep(.el-table td.el-table__cell) {
    background: var(--k-color-surface) !important;
    border-color: var(--k-color-border) !important;
    color: var(--k-color-text) !important;
}

:deep(.el-table th.el-table__cell) {
    background: var(--k-color-surface-soft) !important;
}
</style>

<style>
/* 深色主题：使用全局样式确保能匹配到 data-theme="dark" 在 html 元素上的情况 */
[data-theme="dark"] .el-table .el-table__row.lack-row {
    background-color: #ff4444 !important;
    font-weight: bold !important;
    color: #ffffff !important;
}

[data-theme="dark"] .el-table__body .el-table__row.lack-row {
    background-color: #ff4444 !important;
}
</style>
