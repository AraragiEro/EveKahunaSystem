<script setup lang="ts">
import KEmpty from '@/components/k/KEmpty.vue'
import KCard from '@/components/k/KCard.vue'
import KStat from '@/components/k/KStat.vue'
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
        
        <div class="default-view-container">
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
            
            <KEmpty
                v-if="!loading && assetView.length === 0"
                size="lg"
                why="还没有资产数据"
                hint="先在资产列表刷新一次角色资产，这里会按物品列出数量"
            />
            <!-- 资产网格 -->
            <div class="asset-grid" v-else>
            <KCard 
                v-for="asset in assetView" 
                :key="asset.type_id" 
                class="asset-item-card"
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
                        <KStat
                            label="数量"
                            :value="asset.quantity"
                            unit="个"
                            align="center"
                            tone="success"
                        />
                    </div>
                </div>
                </KCard>
            </div>
        </div>
    </div>
</template>

<style scoped>
.asset-view-dialog-content {
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
    background: var(--k-gradient-toolbar);
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
    color: var(--k-color-text-secondary);
}

.time-label {
    font-weight: 500;
    color: var(--k-color-text-tertiary);
}

.time-value {
    font-weight: 600;
    color: var(--k-color-text);
}

.refresh-button {
    font-size: 14px;
    padding: 10px 20px;
    border-radius: 8px;
    box-shadow: 0 2px 8px color-mix(in srgb, var(--k-color-primary) 20%, transparent);
    transition: all 0.3s ease;
}

.refresh-button:hover {
    box-shadow: 0 4px 12px color-mix(in srgb, var(--k-color-primary) 30%, transparent);
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
    box-shadow: var(--k-shadow-sm);
}

.asset-item-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 12px;
}

.asset-avatar {
    border: 2px solid var(--k-color-border-subtle);
    border-radius: 4px;
}

.asset-info {
    width: 100%;
}

.asset-name-zh {
    font-size: 14px;
    font-weight: 600;
    color: var(--k-color-text);
    margin-bottom: 4px;
    word-break: break-word;
}

.asset-name-en {
    font-size: 12px;
    color: var(--k-color-text-tertiary);
    margin-bottom: 8px;
    word-break: break-word;
}

.asset-quantity {
    margin-top: 4px;
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

