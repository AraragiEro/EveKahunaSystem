<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, UserFilled, Pointer, Close, CircleCheckFilled } from '@element-plus/icons-vue'
import { http } from '@/http'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const token = route.params.token as string

// 认证状态
const isCheckingAuth = ref(true)
const isLoggedIn = computed(() => authStore.isAuthenticated)
const currentUser = computed(() => authStore.user?.username)

// 页面数据
const loading = ref(false)
const workflowData = ref<any[]>([])
const filterSnapshot = ref({})
const planName = ref('')
const errorMessage = ref('')

// 接取记录
const claims = ref<Map<string, any>>(new Map())

// 过滤器
const showOnlyClaimed = ref(false)
const showOnlyMyClaims = ref(false)

// 检查认证状态
const checkAuthStatus = async () => {
    isCheckingAuth.value = true
    try {
        await authStore.checkAuth()
    } catch (error) {
        // 认证检查失败，可能未登录
    }
    isCheckingAuth.value = false
}

// 生成工作流项的唯一key
const getWorkflowItemKey = (item: any): string => {
    // 使用 type_id + runs + fake + avaliable 组合
    const fake = item.bp_object?.fake ?? false
    return `${item.type_id}_${item.runs}_${fake}_${item.avaliable}`
}

// 获取公开工作流数据
const fetchPublicWorkflow = async () => {
    if (!token) {
        errorMessage.value = '缺少分享令牌'
        return
    }

    loading.value = true
    try {
        const res = await http.get(`/public/workflow/${token}`)
        const data = await res.json()
        
        if (data.status !== 200) {
            errorMessage.value = data.message || '获取工作流失败'
            return
        }
        
        planName.value = data.data.plan_name
        filterSnapshot.value = data.data.filter_snapshot || {}
        workflowData.value = data.data.workflow_data || []
        
        // 获取接取记录
        await fetchClaims()
        
    } catch (error: any) {
        errorMessage.value = error.message || '获取工作流失败'
    } finally {
        loading.value = false
    }
}

// 获取接取记录
const fetchClaims = async () => {
    try {
        const res = await http.get(`/public/workflow/${token}/claims`)
        const data = await res.json()
        
        if (data.status === 200) {
            // 转换为Map便于查询
            const claimsMap = new Map()
            data.data.forEach((claim: any) => {
                claimsMap.set(claim.workflow_item_key, claim)
            })
            claims.value = claimsMap
        }
    } catch (error) {
        console.error('获取接取记录失败:', error)
    }
}

// 判断是否已接取
const isClaimed = (item: any): boolean => {
    const key = getWorkflowItemKey(item)
    return claims.value.has(key)
}

// 获取接取人
const getClaimedBy = (item: any): string | null => {
    const key = getWorkflowItemKey(item)
    const claim = claims.value.get(key)
    return claim ? claim.claimed_by : null
}

// 是否当前用户接取
const isClaimedByMe = (item: any): boolean => {
    const key = getWorkflowItemKey(item)
    const claim = claims.value.get(key)
    return claim && claim.claimed_by === currentUser.value
}

// 接取任务
const claimTask = async (item: any) => {
    if (!isLoggedIn.value) {
        goToLogin()
        return
    }
    
    const key = getWorkflowItemKey(item)
    try {
        const res = await http.post(`/public/workflow/${token}/claim`, {
            workflow_item_key: key
        })
        const data = await res.json()
        
        if (data.status === 200) {
            ElMessage.success('任务接取成功')
            // 更新本地状态
            claims.value.set(key, {
                workflow_item_key: key,
                claimed_by: currentUser.value,
                claimed_at: new Date().toISOString()
            })
        } else if (data.status === 409) {
            ElMessage.warning(`该任务已被 ${data.data.claimed_by} 接取`)
            // 刷新接取记录
            await fetchClaims()
        } else {
            ElMessage.error(data.message || '接取失败')
        }
    } catch (error) {
        ElMessage.error('接取失败')
    }
}

// 取消接取
const cancelClaim = async (item: any) => {
    const key = getWorkflowItemKey(item)
    try {
        const res = await http.delete(`/public/workflow/${token}/claim`, {
            workflow_item_key: key
        })
        const data = await res.json()
        
        if (data.status === 200) {
            ElMessage.success('已取消接取')
            claims.value.delete(key)
        } else {
            ElMessage.error(data.message || '取消失败')
        }
    } catch (error) {
        ElMessage.error('取消失败')
    }
}

// 跳转到登录页
const goToLogin = () => {
    router.push({
        path: '/login',
        query: { redirect: route.fullPath }
    })
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

// 处理工作流数据：合并相同流程的项目（参考 WorkFlowView.vue 的逻辑）
const processedWorkflowData = computed(() => {
    // 使用嵌套对象进行分组：type_id -> fake -> avaliable -> runs
    const grouped: Record<string, Record<string, Record<string, Record<string, { count: number, items: any[] }>>>> = {}
    
    workflowData.value.forEach((work: any) => {
        const typeId = String(work.type_id)
        const fake = work.bp_object?.fake ?? false
        const fakeKey = String(fake)
        const avaliable = work.avaliable ?? false
        const avaliableKey = String(avaliable)
        const runs = work.runs
        const runsKey = String(runs)
        
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
        if (!(runsKey in grouped[typeId][fakeKey][avaliableKey])) {
            grouped[typeId][fakeKey][avaliableKey][runsKey] = {
                count: 0,
                items: []
            }
        }
        
        // 统计计数和收集项目
        grouped[typeId][fakeKey][avaliableKey][runsKey].count++
        grouped[typeId][fakeKey][avaliableKey][runsKey].items.push(work)
    })
    
    // 扁平化为数组
    const result: any[] = []
    Object.keys(grouped).forEach(typeId => {
        const typeIdNum = parseInt(typeId)
        Object.keys(grouped[typeId]).forEach(fakeKey => {
            const fake = fakeKey === 'true'
            Object.keys(grouped[typeId][fakeKey]).forEach(avaliableKey => {
                const avaliable = avaliableKey === 'true'
                Object.keys(grouped[typeId][fakeKey][avaliableKey]).forEach(runsStr => {
                    const runs = parseInt(runsStr)
                    const groupData = grouped[typeId][fakeKey][avaliableKey][runsStr]
                    // 使用第一个项目作为基础，添加 runs_count
                    const baseItem = groupData.items[0]
                    result.push({
                        ...baseItem,
                        runs_count: groupData.count
                    })
                })
            })
        })
    })
    
    return result
})

// 过滤后的工作流数据
const filteredWorkflowData = computed(() => {
    let data = processedWorkflowData.value
    
    // 显示已接取的任务
    if (showOnlyClaimed.value) {
        data = data.filter(item => isClaimed(item))
    }
    
    // 只显示我接取的任务
    if (showOnlyMyClaims.value && isLoggedIn.value) {
        data = data.filter(item => isClaimedByMe(item))
    }
    
    return data
})

onMounted(() => {
    checkAuthStatus()
    fetchPublicWorkflow()
})
</script>

<template>
    <div class="public-workflow-container">
        <!-- 头部 -->
        <div class="workflow-header">
            <h1 class="page-title">工作流视图</h1>
            <div class="page-subtitle">{{ planName }}</div>
            
            <!-- 登录/用户信息栏 -->
            <div class="auth-bar">
                <template v-if="isCheckingAuth">
                    <el-skeleton :rows="1" animated style="width: 150px" />
                </template>
                <template v-else-if="isLoggedIn">
                    <div class="user-info">
                        <el-icon><User /></el-icon>
                        <span>{{ currentUser }}</span>
                        <el-button link type="primary" @click="authStore.logout()">
                            退出
                        </el-button>
                    </div>
                </template>
                <template v-else>
                    <el-button type="primary" @click="goToLogin">
                        <el-icon><User /></el-icon>
                        登录以接取任务
                    </el-button>
                </template>
            </div>
        </div>
        
        <!-- 内容区域 -->
        <div v-loading="loading" class="workflow-content">
            <!-- 错误状态 -->
            <div v-if="errorMessage" class="error-state">
                <el-result
                    icon="error"
                    :title="errorMessage"
                    sub-title="请检查链接是否正确或联系分享者"
                />
            </div>
            
            <!-- 工作流表格（带接取功能） -->
            <template v-else>
                <!-- 过滤器栏 -->
                <div class="filter-bar">
                    <el-checkbox v-model="showOnlyClaimed">
                        只显示已接取任务
                    </el-checkbox>
                    <el-checkbox v-model="showOnlyMyClaims" :disabled="!isLoggedIn">
                        只显示我接取的任务
                    </el-checkbox>
                </div>
                
                <el-table
                    :data="filteredWorkflowData"
                    border
                    max-height="70vh"
                >
                    <el-table-column label="icon" width="80">
                        <template #default="{ row }">
                            <img :src="`https://imageserver.eveonline.com/types/${row.type_id}/icon`" alt="类型" width="32" height="32" />
                        </template>
                    </el-table-column>
                    <el-table-column label="物品id" prop="type_id" width="90" />
                    <el-table-column label="物品名" width="180">
                        <template #default="{ row }">
                            <div>{{ row.type_name_zh || row.type_name }}</div>
                        </template>
                    </el-table-column>
                    <el-table-column label="线" prop="runs_count" width="100">
                        <template #default="{ row }">
                            {{ formatAccounting(row.runs_count) }}
                        </template>
                    </el-table-column>
                    <el-table-column label="流程" prop="runs" width="80" />
                    <el-table-column label="材料满足" width="90">
                        <template #default="{ row }">
                            <el-icon v-if="row.avaliable" size="18" style="color: #67c23a;"><CircleCheckFilled /></el-icon>
                            <el-icon v-else size="18" style="color: #f56c6c;"><Close /></el-icon>
                        </template>
                    </el-table-column>
                    <el-table-column label="分配蓝图" width="90">
                        <template #default="{ row }">
                            <el-icon v-if="row.fake" size="18" style="color: #f56c6c;"><Close /></el-icon>
                            <el-icon v-else size="18" style="color: #67c23a;"><CircleCheckFilled /></el-icon>
                        </template>
                    </el-table-column>
                    <el-table-column label="工作类型" width="100">
                        <template #default="{ row }">
                            <span v-if="row.active_id === 1">制造</span>
                            <span v-else-if="row.active_id === 11">反应</span>
                            <span v-else>未知</span>
                        </template>
                    </el-table-column>
                    <el-table-column label="产物类型" prop="class_type" width="120" />
                    <el-table-column label="EIV" width="120">
                        <template #default="{ row }">
                            {{ formatAccounting(row.eiv) }}
                        </template>
                    </el-table-column>
                    <el-table-column label="估计时间" width="120">
                        <template #default="{ row }">
                            {{ formatDuration(row.active_time) }}
                        </template>
                    </el-table-column>
                    
                    <!-- 接取状态列 -->
                    <el-table-column label="接取状态" width="140" fixed="right">
                        <template #default="{ row }">
                            <div class="claim-cell">
                                <!-- 状态A: 未登录 -->
                                <template v-if="!isLoggedIn">
                                    <el-button link type="info" @click="goToLogin">
                                        登录后接取
                                    </el-button>
                                </template>
                                
                                <!-- 状态D: 已被他人接取 -->
                                <template v-else-if="isClaimed(row) && !isClaimedByMe(row)">
                                    <el-tag type="info" size="small">
                                        <el-icon><UserFilled /></el-icon>
                                        {{ getClaimedBy(row) }}
                                    </el-tag>
                                </template>
                                
                                <!-- 状态C: 当前用户已接取（显示取消按钮） -->
                                <template v-else-if="isClaimedByMe(row)">
                                    <el-button 
                                        type="danger" 
                                        size="small"
                                        @click="cancelClaim(row)"
                                    >
                                        <el-icon><Close /></el-icon>
                                        取消接取
                                    </el-button>
                                </template>
                                
                                <!-- 状态B: 未接取（显示接取按钮） -->
                                <template v-else>
                                    <el-button 
                                        type="primary" 
                                        size="small"
                                        @click="claimTask(row)"
                                    >
                                        <el-icon><Pointer /></el-icon>
                                        接取
                                    </el-button>
                                </template>
                            </div>
                        </template>
                    </el-table-column>
                </el-table>
            </template>
        </div>
    </div>
</template>

<style scoped>
.public-workflow-container {
    min-height: 100vh;
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    padding: 40px 20px;
}

:global([data-theme="dark"]) .public-workflow-container {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
}

.workflow-header {
    max-width: 1400px;
    margin: 0 auto 32px;
    text-align: center;
    position: relative;
}

.page-title {
    font-size: 32px;
    font-weight: 600;
    color: #2c3e50;
    margin: 0 0 8px 0;
}

:global([data-theme="dark"]) .page-title {
    color: #e0e0e0;
}

.page-subtitle {
    font-size: 16px;
    color: #64748b;
    margin: 0;
}

:global([data-theme="dark"]) .page-subtitle {
    color: #a0a0a0;
}

.auth-bar {
    position: absolute;
    top: 0;
    right: 0;
}

.user-info {
    display: flex;
    align-items: center;
    gap: 8px;
    background: white;
    padding: 8px 16px;
    border-radius: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

:global([data-theme="dark"]) .user-info {
    background: #2d2d3a;
    color: #e0e0e0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}

.workflow-content {
    max-width: 1400px;
    margin: 0 auto;
}

.filter-bar {
    background: white;
    padding: 16px 20px;
    border-radius: 8px;
    margin-bottom: 16px;
    display: flex;
    gap: 24px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

:global([data-theme="dark"]) .filter-bar {
    background: #2d2d3a;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
}

.error-state {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 400px;
    background: white;
    border-radius: 8px;
    padding: 40px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

:global([data-theme="dark"]) .error-state {
    background: #2d2d3a;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
}

.claim-cell {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
}
</style>

<style>
/* 深色模式样式 - 全局生效 */
[data-theme="dark"] .public-workflow-container {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
}

[data-theme="dark"] .page-title {
    color: #e0e0e0;
}

[data-theme="dark"] .page-subtitle {
    color: #a0a0a0;
}

[data-theme="dark"] .user-info {
    background: #2d2d3a;
    color: #e0e0e0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}

[data-theme="dark"] .filter-bar {
    background: #2d2d3a;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
}

[data-theme="dark"] .error-state {
    background: #2d2d3a;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
}

/* 表格深色模式样式 - 提高对比度 */
[data-theme="dark"] .el-table {
    background-color: #1e1e2d;
    color: #e0e0e0;
}

[data-theme="dark"] .el-table__header-wrapper th.el-table__cell {
    background-color: #2d2d3a;
    color: #ffffff;
}

[data-theme="dark"] .el-table__body-wrapper td.el-table__cell {
    background-color: #1e1e2d;
    color: #e0e0e0;
}

[data-theme="dark"] .el-table--border .el-table__cell {
    border-color: #3d3d4a;
}

[data-theme="dark"] .el-table--enable-row-hover .el-table__body tr:hover > td.el-table__cell {
    background-color: #2d2d3a;
}
</style>
