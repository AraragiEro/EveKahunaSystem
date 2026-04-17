<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument, Link, Refresh } from '@element-plus/icons-vue'
import { http } from '@/http'

interface Props {
    modelValue: boolean
    planName: string
    filterSnapshot: object
}

const props = defineProps<Props>()
const emit = defineEmits<{
    'update:modelValue': [value: boolean]
    'share-created': [shareData: { shareToken: string; shareUrl: string }]
    'share-token-updated': [shareToken: string | null]
}>()

const loading = ref(false)
const shareResult = ref<{
    shareToken: string
    shareUrl: string
} | null>(null)

// 已有分享状态
const existingShareStatus = ref<{
    public: boolean
    shareToken: string | null
    shareUrl: string | null
    hasSnapshot: boolean
} | null>(null)
const checkingStatus = ref(false)

const dialogVisible = computed({
    get: () => props.modelValue,
    set: (val) => emit('update:modelValue', val)
})

// 监听对话框打开，获取分享状态
watch(() => props.modelValue, (newVal) => {
    if (newVal && props.planName) {
        fetchShareStatus()
    }
})

// 获取已有分享状态
const fetchShareStatus = async () => {
    if (!props.planName) return
    
    checkingStatus.value = true
    try {
        const res = await http.get(`/public/workflow/share/status?plan_name=${encodeURIComponent(props.planName)}`)
        const data = await res.json()
        
        if (data.status === 200) {
            existingShareStatus.value = {
                public: data.data.public,
                shareToken: data.data.share_token,
                shareUrl: data.data.share_url,
                hasSnapshot: data.data.has_snapshot
            }
            
            // 如果已有分享链接且处于公开状态，直接显示结果
            if (data.data.public && data.data.share_url) {
                shareResult.value = {
                    shareToken: data.data.share_token,
                    shareUrl: data.data.share_url
                }
            }
            
            // 通知父组件 shareToken 更新
            emit('share-token-updated', data.data.share_token)
        }
    } catch (error) {
        console.error('获取分享状态失败:', error)
    } finally {
        checkingStatus.value = false
    }
}

// 切换分享公开状态
const toggleShareStatus = async () => {
    if (!props.planName) return
    
    loading.value = true
    try {
        const res = await http.post('/public/workflow/share/toggle', {
            plan_name: props.planName
        })
        const data = await res.json()
        
        if (data.status === 200) {
            ElMessage.success(data.message)
            // 刷新状态
            await fetchShareStatus()
        } else {
            ElMessage.error(data.message || '操作失败')
        }
    } catch (error) {
        ElMessage.error('操作失败')
        console.error(error)
    } finally {
        loading.value = false
    }
}

// 重新创建分享
const recreateShare = async () => {
    shareResult.value = null
    await createShare()
}

// 创建分享
const createShare = async () => {
    loading.value = true
    try {
        const res = await http.post('/public/workflow/share', {
            plan_name: props.planName,
            filter_snapshot: props.filterSnapshot
        })
        const data = await res.json()
        
        if (data.status === 200) {
            shareResult.value = {
                shareToken: data.share_token,
                shareUrl: data.share_url
            }
            emit('share-created', {
                shareToken: data.share_token,
                shareUrl: data.share_url
            })
            ElMessage.success('分享链接创建成功')
        } else {
            ElMessage.error(data.message || '创建分享失败')
        }
    } catch (error) {
        ElMessage.error('创建分享失败')
        console.error(error)
    } finally {
        loading.value = false
    }
}

// 复制分享链接
const copyShareUrl = async () => {
    if (!shareResult.value) return
    try {
        await navigator.clipboard.writeText(shareResult.value.shareUrl)
        ElMessage.success('链接已复制到剪贴板')
    } catch (err) {
        ElMessage.error('复制失败')
    }
}

// 关闭对话框
const closeDialog = () => {
    dialogVisible.value = false
    shareResult.value = null
}

// 对话框关闭后的清理
const handleClosed = () => {
    shareResult.value = null
    existingShareStatus.value = null
}
</script>

<template>
    <el-dialog
        v-model="dialogVisible"
        title="分享工作流"
        width="550px"
        :close-on-click-modal="false"
        @closed="handleClosed"
    >
        <!-- 加载中 -->
        <div v-if="checkingStatus" class="share-loading">
            <el-skeleton :rows="3" animated />
        </div>
        
        <!-- 已有分享链接且公开 - 显示链接和复制 -->
        <div v-else-if="shareResult" class="share-result">
            <el-result
                icon="success"
                title="分享链接"
                :sub-title="`分享ID: ${shareResult.shareToken}`"
            />
            <div class="share-url-box">
                <el-input
                    v-model="shareResult.shareUrl"
                    readonly
                    :prefix-icon="Link"
                />
                <el-button 
                    type="primary" 
                    :icon="CopyDocument"
                    @click="copyShareUrl"
                >
                    复制
                </el-button>
            </div>
            <div class="share-actions-existing">
                <el-button 
                    type="warning" 
                    :icon="Refresh"
                    :loading="loading"
                    @click="recreateShare"
                >
                    重新创建
                </el-button>
                <el-button 
                    @click="toggleShareStatus"
                    :loading="loading"
                >
                    关闭分享
                </el-button>
            </div>
            <p class="share-hint">
                提示：重新创建后旧链接将自动失效。
            </p>
        </div>
        
        <!-- 已有分享链接但未公开 - 显示开启分享按钮 -->
        <div v-else-if="existingShareStatus?.shareToken" class="share-create">
            <el-result
                icon="info"
                title="分享已关闭"
                :sub-title="`分享ID: ${existingShareStatus.shareToken}`"
            />
            <p class="share-info">该计划已有分享链接，但当前处于关闭状态</p>
            <div class="share-actions">
                <el-button @click="closeDialog">取消</el-button>
                <el-button 
                    type="success" 
                    :loading="loading"
                    @click="toggleShareStatus"
                >
                    开启分享
                </el-button>
                <el-button 
                    type="primary" 
                    :icon="Refresh"
                    :loading="loading"
                    @click="recreateShare"
                >
                    重新创建
                </el-button>
            </div>
        </div>
        
        <!-- 没有分享链接 - 创建界面 -->
        <div v-else class="share-create">
            <p>即将为计划 <strong>{{ planName }}</strong> 创建分享链接</p>
            <p class="share-info">分享的链接将包含当前的过滤条件设置</p>
            <div class="share-actions">
                <el-button @click="closeDialog">取消</el-button>
                <el-button 
                    type="primary" 
                    :loading="loading"
                    @click="createShare"
                >
                    创建分享链接
                </el-button>
            </div>
        </div>
    </el-dialog>
</template>

<style scoped>
.share-create {
    text-align: center;
    padding: 20px;
}

.share-info {
    color: #909399;
    font-size: 14px;
    margin-top: 8px;
}

.share-actions {
    margin-top: 24px;
    display: flex;
    justify-content: center;
    gap: 12px;
}

.share-result {
    padding: 0 20px 20px;
}

.share-url-box {
    display: flex;
    gap: 8px;
    margin-top: 16px;
}

.share-hint {
    text-align: center;
    color: #909399;
    font-size: 12px;
    margin-top: 16px;
    line-height: 1.6;
}

.share-loading {
    padding: 20px;
}

.share-actions-existing {
    margin-top: 20px;
    display: flex;
    justify-content: center;
    gap: 12px;
}
</style>
