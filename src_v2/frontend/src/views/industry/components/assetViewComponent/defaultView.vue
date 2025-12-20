<script setup lang="ts">
import { computed } from 'vue'
import { Refresh } from '@element-plus/icons-vue'

interface AssetItem {
    type_id: number
    type_name: string
    type_name_zh?: string
    quantity: number
}

interface Props {
    loading: boolean
    assetView: AssetItem[]
    lastUpdateTime?: number | string | Date
}

const props = defineProps<Props>()

const emit = defineEmits<{
    refresh: []
}>()

// 计算 lastUpdateTime，如果没有传入则返回 undefined（formatTime 会处理）
const lastUpdateTime = computed(() => {
    return props.lastUpdateTime
})

// 格式化时间
const formatTime = (time?: number | string | Date): string => {
    if (!time) return '未知'
    
    let date: Date
    if (typeof time === 'number') {
        // 如果是时间戳（毫秒），直接使用；如果是秒级时间戳，转换为毫秒
        date = time > 1e12 ? new Date(time) : new Date(time * 1000)
    } else if (typeof time === 'string') {
        date = new Date(time)
    } else {
        date = time
    }
    
    if (isNaN(date.getTime())) {
        return '未知'
    }
    
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    const seconds = String(date.getSeconds()).padStart(2, '0')
    
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}

// 处理刷新
const handleRefresh = () => {
    emit('refresh')
}
</script>

<template>
    <div v-loading="loading" class="asset-view-dialog-content">
        <div v-if="!loading && assetView.length === 0" class="empty-state">
            <el-empty description="暂无数据" />
        </div>
        <div v-else class="default-view-container">
            <!-- 工具栏 -->
            <div class="toolbar">
                <div class="toolbar-right">
                    <div class="last-update-time">
                        <span class="time-label">上次获取时间：</span>
                        <span class="time-value">{{ formatTime(lastUpdateTime) }}</span>
                    </div>
                    <el-button 
                        type="primary" 
                        :icon="Refresh"
                        @click="handleRefresh"
                        :loading="loading"
                        class="refresh-button"
                    >
                        立即刷新
                    </el-button>
                </div>
            </div>
            
            <!-- 资产网格 -->
            <div class="asset-grid">
            <el-card 
                v-for="asset in assetView" 
                :key="asset.type_id" 
                class="asset-item-card"
                shadow="hover"
            >
                <div class="asset-item-content">
                    <el-avatar 
                        :size="64" 
                        :src="`https://imageserver.eveonline.com/Type/${asset.type_id}_64.png`" 
                        shape="square"
                        class="asset-avatar"
                    />
                    <div class="asset-info">
                        <div class="asset-name-zh">{{ asset.type_name_zh || asset.type_name }}</div>
                        <div class="asset-name-en">{{ asset.type_name }}</div>
                        <el-tag type="success" class="asset-quantity" size="large">{{ asset.quantity }} 个</el-tag>
                    </div>
                </div>
                </el-card>
            </div>
        </div>
    </div>
</template>

<style scoped>
.asset-view-dialog-content {
    min-height: 400px;
}

.empty-state {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 400px;
}

.default-view-container {
    display: flex;
    flex-direction: column;
    gap: 20px;
}

/* 工具栏 */
.toolbar {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 12px;
    padding: 16px;
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    border-radius: 8px;
}

.toolbar-right {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-shrink: 0;
}

.last-update-time {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    color: #606266;
}

.time-label {
    font-weight: 500;
    color: #909399;
}

.time-value {
    font-weight: 600;
    color: #303133;
}

.refresh-button {
    font-size: 14px;
    padding: 10px 20px;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
    transition: all 0.3s ease;
}

.refresh-button:hover {
    box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
    transform: translateY(-1px);
}

.asset-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 16px;
    padding: 8px;
}

.asset-item-card {
    transition: all 0.3s ease;
}

.asset-item-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.asset-item-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 12px;
}

.asset-avatar {
    border: 2px solid #f0f0f0;
    border-radius: 4px;
}

.asset-info {
    width: 100%;
}

.asset-name-zh {
    font-size: 14px;
    font-weight: 600;
    color: #303133;
    margin-bottom: 4px;
    word-break: break-word;
}

.asset-name-en {
    font-size: 12px;
    color: #909399;
    margin-bottom: 8px;
    word-break: break-word;
}

.asset-quantity {
    font-size: 15px;
    font-weight: 600;
    padding: 6px 12px;
    margin-top: 4px;
    display: inline-block;
    box-shadow: 0 2px 4px rgba(103, 194, 58, 0.2);
}

/* 响应式设计 */
@media (max-width: 768px) {
    .toolbar {
        flex-direction: column;
        align-items: stretch;
    }
    
    .toolbar-right {
        width: 100%;
        flex-direction: column;
        align-items: stretch;
        gap: 12px;
    }
    
    .last-update-time {
        justify-content: center;
        width: 100%;
    }
    
    .refresh-button {
        width: 100%;
    }
    
    .asset-grid {
        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
        gap: 12px;
    }
}
</style>

