<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'

interface Props {
    modelValue: boolean
    workflowItem: any | null
    existingClaims: any
    currentUser: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
    'update:modelValue': [value: boolean]
    'confirm': [quantity: number]
}>()

const quantity = ref(1)
const loading = ref(false)

const dialogVisible = computed({
    get: () => props.modelValue,
    set: (val) => emit('update:modelValue', val)
})

// 计算总线数
const totalLines = computed(() => {
    return props.workflowItem?.line_count || 1
})

// 计算已接取数量
const claimedLines = computed(() => {
    if (!props.workflowItem) return 0
    const key = getWorkflowItemKey(props.workflowItem)
    const claimData = props.existingClaims.get(key)
    return claimData?.claimed_lines || 0
})

// 计算剩余可接取数量
const remainingLines = computed(() => {
    return totalLines.value - claimedLines.value
})

// 计算当前用户已接取数量
const myClaimedLines = computed(() => {
    if (!props.workflowItem || !props.currentUser) return 0
    const key = getWorkflowItemKey(props.workflowItem)
    const claimData = props.existingClaims.get(key)
    const claims = claimData?.claims || []
    const myClaim = claims.find((c: any) => c.claimed_by === props.currentUser)
    return myClaim?.claimed_quantity || 0
})

// 生成工作流项的唯一key
const getWorkflowItemKey = (item: any): string => {
    const fake = item.bp_object?.fake ?? false
    return `${item.type_id}_${item.runs}_${fake}_${item.avaliable}`
}

// 监听对话框打开，重置数量
watch(() => props.modelValue, (newVal) => {
    if (newVal) {
        quantity.value = remainingLines.value > 0 ? remainingLines.value : 1
    }
})

// 确认接取
const handleConfirm = () => {
    if (quantity.value < 1) {
        ElMessage.warning('接取数量必须大于0')
        return
    }
    if (quantity.value > remainingLines.value) {
        ElMessage.warning(`最多只能接取 ${remainingLines.value} 线`)
        return
    }
    emit('confirm', quantity.value)
    dialogVisible.value = false
}

// 快速设置数量
const setQuantity = (value: number) => {
    quantity.value = Math.min(value, remainingLines.value)
}
</script>

<template>
    <el-dialog
        v-model="dialogVisible"
        :title="myClaimedLines > 0 ? '追加接取' : '接取任务'"
        width="400px"
        :close-on-click-modal="false"
    >
        <div v-if="workflowItem" class="claim-dialog-content">
            <!-- 任务信息 -->
            <div class="task-info">
                <div class="task-name">{{ workflowItem.type_name_zh || workflowItem.type_name }}</div>
                <div class="task-detail">
                    <el-tag size="small">{{ workflowItem.runs }}流程</el-tag>
                    <el-tag size="small" type="info">共 {{ totalLines }} 线</el-tag>
                </div>
            </div>

            <!-- 接取状态 -->
            <div class="claim-status">
                <div class="status-row">
                    <span class="status-label">已接取:</span>
                    <el-progress 
                        :percentage="Math.round((claimedLines / totalLines) * 100)" 
                        :format="() => `${claimedLines}/${totalLines}`"
                        :status="claimedLines >= totalLines ? 'success' : ''"
                    />
                </div>
                <div v-if="myClaimedLines > 0" class="my-claim">
                    您已接取: <strong>{{ myClaimedLines }}</strong> 线
                </div>
                <div class="remaining">
                    剩余可接取: <strong>{{ remainingLines }}</strong> 线
                </div>
            </div>

            <!-- 数量输入 -->
            <div class="quantity-input-section">
                <div class="input-label">接取数量:</div>
                <el-input-number 
                    v-model="quantity" 
                    :min="1" 
                    :max="remainingLines"
                    :disabled="remainingLines <= 0"
                    style="width: 150px"
                />
                <span class="unit">线</span>
            </div>

            <!-- 快捷按钮 -->
            <div class="quick-buttons">
                <el-button 
                    size="small" 
                    @click="setQuantity(1)"
                    :disabled="remainingLines < 1"
                >
                    1线
                </el-button>
                <el-button 
                    size="small" 
                    @click="setQuantity(Math.floor(remainingLines / 2))"
                    :disabled="remainingLines < 2"
                >
                    一半
                </el-button>
                <el-button 
                    size="small" 
                    type="primary" 
                    @click="setQuantity(remainingLines)"
                    :disabled="remainingLines <= 0"
                >
                    全部剩余
                </el-button>
            </div>
        </div>

        <template #footer>
            <div class="dialog-footer">
                <el-button @click="dialogVisible = false">取消</el-button>
                <el-button 
                    type="primary" 
                    @click="handleConfirm"
                    :disabled="remainingLines <= 0 || quantity < 1"
                >
                    {{ myClaimedLines > 0 ? '追加接取' : '确认接取' }}
                </el-button>
            </div>
        </template>
    </el-dialog>
</template>

<style scoped>
.claim-dialog-content {
    padding: 0 10px;
}

.task-info {
    text-align: center;
    margin-bottom: 20px;
    padding-bottom: 15px;
    border-bottom: 1px solid #e4e7ed;
}

.task-name {
    font-size: 16px;
    font-weight: 600;
    color: var(--k-color-text);
    margin-bottom: 8px;
}

.task-detail {
    display: flex;
    justify-content: center;
    gap: 8px;
}

.claim-status {
    margin-bottom: 20px;
}

.status-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
}

.status-label {
    font-size: 14px;
    color: var(--k-color-text-secondary);
    white-space: nowrap;
}

:deep(.el-progress) {
    flex: 1;
}

.my-claim {
    font-size: 13px;
    color: #409eff;
    margin-bottom: 5px;
}

.remaining {
    font-size: 14px;
    color: #67c23a;
    font-weight: 500;
}

.remaining strong {
    color: #67c23a;
    font-size: 16px;
}

.quantity-input-section {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 15px;
}

.input-label {
    font-size: 14px;
    color: var(--k-color-text-secondary);
}

.unit {
    font-size: 14px;
    color: var(--k-color-text-secondary);
}

.quick-buttons {
    display: flex;
    justify-content: center;
    gap: 8px;
}

.dialog-footer {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
}
</style>