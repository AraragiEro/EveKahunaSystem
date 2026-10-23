<script setup lang="ts">
import KEmpty from '@/components/k/KEmpty.vue'
import KStat from '@/components/k/KStat.vue'
import KTable from '@/components/k/KTable.vue'
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, User, RefreshRight } from '@element-plus/icons-vue'
import { http } from '@/http'

interface Claim {
    workflow_item_key: string
    claimed_by: string
    claimed_at: string
    status: string
    claimed_quantity: number
}

interface Props {
    modelValue: boolean
    planName: string
    shareToken: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
    'update:modelValue': [value: boolean]
    'claim-updated': []
}>()

const loading = ref(false)
const claims = ref<Claim[]>([])
const transferUsername = ref('')
const currentTransferClaim = ref<Claim | null>(null)
const showTransferDialog = ref(false)

const dialogVisible = computed({
    get: () => props.modelValue,
    set: (val) => emit('update:modelValue', val)
})

// 监听对话框打开，获取接取记录
watch(() => props.modelValue, (newVal) => {
    if (newVal && props.shareToken) {
        fetchClaims()
    }
})

// 获取接取记录
const fetchClaims = async () => {
    if (!props.shareToken) return
    
    loading.value = true
    try {
        const res = await http.get(`/public/workflow/${props.shareToken}/claims`)
        const data = await res.json()
        
        if (data.status === 200) {
            // 新格式：按工作流项分组的对象
            const claimsList: Claim[] = []
            Object.entries(data.data || {}).forEach(([key, value]: [string, any]) => {
                if (value.claims && Array.isArray(value.claims)) {
                    value.claims.forEach((claim: any) => {
                        claimsList.push({
                            workflow_item_key: key,
                            claimed_by: claim.claimed_by,
                            claimed_at: claim.claimed_at,
                            status: claim.status,
                            claimed_quantity: claim.claimed_quantity
                        })
                    })
                }
            })
            claims.value = claimsList
        } else {
            ElMessage.error(data.message || '获取接取记录失败')
        }
    } catch (error) {
        console.error('获取接取记录失败:', error)
        ElMessage.error('获取接取记录失败')
    } finally {
        loading.value = false
    }
}

// 解析 workflow_item_key 获取任务信息
const parseWorkflowItemKey = (key: string) => {
    const parts = key.split('_')
    if (parts.length >= 4) {
        return {
            type_id: parts[0],
            runs: parts[1],
            fake: parts[2] === 'true' ? '假蓝图' : '真蓝图',
            available: parts[3] === 'true' ? '有材料' : '无材料'
        }
    }
    return { type_id: key, runs: '-', fake: '-', available: '-' }
}

// 删除接取
const handleDeleteClaim = async (claim: Claim) => {
    try {
        await ElMessageBox.confirm(
            `确定要删除该接取记录吗？\n接取人: ${claim.claimed_by}\n数量: ${claim.claimed_quantity} 线`,
            '确认删除',
            {
                confirmButtonText: '确定',
                cancelButtonText: '取消',
                type: 'warning'
            }
        )
        
        loading.value = true
        const res = await http.post(`/public/workflow/${props.shareToken}/claim/manage/delete`, {
            workflow_item_key: claim.workflow_item_key
        })
        const data = await res.json()
        
        if (data.status === 200) {
            ElMessage.success('删除成功')
            await fetchClaims()
            emit('claim-updated')
        } else {
            ElMessage.error(data.message || '删除失败')
        }
    } catch (error: any) {
        if (error !== 'cancel') {
            console.error('删除接取失败:', error)
            ElMessage.error('删除失败')
        }
    } finally {
        loading.value = false
    }
}

// 打开转移对话框
const openTransferDialog = (claim: Claim) => {
    currentTransferClaim.value = claim
    transferUsername.value = ''
    showTransferDialog.value = true
}

// 转移接取给新用户
const handleTransferClaim = async () => {
    if (!transferUsername.value.trim()) {
        ElMessage.warning('请输入新用户名')
        return
    }
    
    if (!currentTransferClaim.value) return
    
    try {
        loading.value = true
        const res = await http.post(`/public/workflow/${props.shareToken}/claim/manage/transfer`, {
            workflow_item_key: currentTransferClaim.value.workflow_item_key,
            new_claimed_by: transferUsername.value.trim()
        })
        const data = await res.json()
        
        if (data.status === 200) {
            ElMessage.success('转移成功')
            showTransferDialog.value = false
            await fetchClaims()
            emit('claim-updated')
        } else {
            ElMessage.error(data.message || '转移失败')
        }
    } catch (error) {
        console.error('转移接取失败:', error)
        ElMessage.error('转移失败')
    } finally {
        loading.value = false
    }
}

// 关闭对话框
const closeDialog = () => {
    dialogVisible.value = false
}

// 格式化时间
const formatTime = (timeStr: string) => {
    if (!timeStr) return '-'
    const date = new Date(timeStr)
    return date.toLocaleString('zh-CN')
}
</script>

<template>
    <el-dialog
        v-model="dialogVisible"
        title="接取管理"
        width="900px"
        :close-on-click-modal="false"
    >
        <div v-if="!shareToken" class="no-share-token">
            <KEmpty why="请先创建分享链接" />
        </div>
        
        <div v-else v-loading="loading" class="claim-manage-content">
            <!-- 统计信息 -->
            <div class="claim-stats">
                <KStat label="接取记录数" :value="claims.length" />
                <KStat
                    label="总接取线数"
                    :value="claims.reduce((sum, c) => sum + (c.claimed_quantity || 0), 0)"
                />
            </div>
            
            <!-- 接取列表 -->
            <KTable
                :data="claims"
                border
                style="width: 100%; margin-top: 16px"
                max-height="400"
                empty-why="还没有人接取这个计划的工作流"
                empty-hint="把计划分享给生产成员后，接取记录会出现在这里"
            >
                <el-table-column label="任务信息" min-width="200">
                    <template #default="{ row }">
                        <div class="task-info">
                            <div class="task-key">{{ row.workflow_item_key }}</div>
                            <div class="task-detail">
                                <el-tag size="small" type="info">
                                    流程: {{ parseWorkflowItemKey(row.workflow_item_key).runs }}
                                </el-tag>
                                <el-tag size="small" :type="parseWorkflowItemKey(row.workflow_item_key).fake === '假蓝图' ? 'danger' : 'success'">
                                    {{ parseWorkflowItemKey(row.workflow_item_key).fake }}
                                </el-tag>
                                <el-tag size="small" :type="parseWorkflowItemKey(row.workflow_item_key).available === '有材料' ? 'success' : 'warning'">
                                    {{ parseWorkflowItemKey(row.workflow_item_key).available }}
                                </el-tag>
                            </div>
                        </div>
                    </template>
                </el-table-column>
                
                <el-table-column label="接取人" prop="claimed_by" width="100" />
                
                <el-table-column label="接取数量" width="90">
                    <template #default="{ row }">
                        <el-tag type="primary" size="small">{{ row.claimed_quantity }} 线</el-tag>
                    </template>
                </el-table-column>
                
                <el-table-column label="接取时间" width="150">
                    <template #default="{ row }">
                        {{ formatTime(row.claimed_at) }}
                    </template>
                </el-table-column>
                
                <el-table-column label="状态" width="100">
                    <template #default="{ row }">
                        <el-tag :type="row.status === 'claimed' ? 'primary' : 'success'">
                            {{ row.status === 'claimed' ? '已接取' : row.status }}
                        </el-tag>
                    </template>
                </el-table-column>
                
                <el-table-column label="操作" width="180" fixed="right">
                    <template #default="{ row }">
                        <el-button
                            type="primary"
                            size="small"
                            :icon="User"
                            @click="openTransferDialog(row)"
                        >
                            更改用户
                        </el-button>
                        <el-button
                            type="danger"
                            size="small"
                            :icon="Delete"
                            @click="handleDeleteClaim(row)"
                        >
                            删除
                        </el-button>
                    </template>
                </el-table-column>
            </KTable>
            
            <!-- 空状态 -->
            <KEmpty v-if="claims.length === 0 && !loading" why="暂无接取记录" />
        </div>
        
        <template #footer>
            <div class="dialog-footer">
                <el-button @click="closeDialog">关闭</el-button>
                <el-button type="primary" :icon="RefreshRight" @click="fetchClaims" :loading="loading">
                    刷新
                </el-button>
            </div>
        </template>
    </el-dialog>
    
    <!-- 转移对话框 -->
    <el-dialog
        v-model="showTransferDialog"
        title="更改接取用户"
        width="400px"
        :close-on-click-modal="false"
    >
        <div v-if="currentTransferClaim" class="transfer-content">
            <p>任务: {{ currentTransferClaim.workflow_item_key }}</p>
            <p>当前接取人: {{ currentTransferClaim.claimed_by }}</p>
            <p>接取数量: <strong>{{ currentTransferClaim.claimed_quantity }} 线</strong></p>
            <el-input
                v-model="transferUsername"
                placeholder="请输入新用户名"
                style="margin-top: 16px"
            />
        </div>
        <template #footer>
            <div class="dialog-footer">
                <el-button @click="showTransferDialog = false">取消</el-button>
                <el-button type="primary" @click="handleTransferClaim" :loading="loading">
                    确认转移
                </el-button>
            </div>
        </template>
    </el-dialog>
</template>

<style scoped>
.claim-manage-content {
    padding: 0;
}

.no-share-token {
    padding: 40px;
    text-align: center;
}

.claim-stats {
    margin-bottom: 16px;
}

.task-info {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.task-key {
    font-family: monospace;
    font-size: 12px;
    color: var(--k-color-text-secondary);
    word-break: break-all;
}

.task-detail {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
}

.dialog-footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
}

.transfer-content p {
    margin: 8px 0;
    color: var(--k-color-text-secondary);
}
</style>
