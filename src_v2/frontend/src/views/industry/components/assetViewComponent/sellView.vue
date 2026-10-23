<script setup lang="ts">
import KEmpty from '@/components/k/KEmpty.vue'
import KCard from '@/components/k/KCard.vue'
import KStat from '@/components/k/KStat.vue'
import { ref, computed } from 'vue'
import { Setting, Search, Refresh } from '@element-plus/icons-vue'

interface AssetItem {
    type_id: number
    type_name: string
    type_name_zh?: string
    quantity: number
    price: number
}

interface Props {
    loading: boolean
    assetView: AssetItem[],
    view_type: string,
    config: {
        price_base: string,
        percent: number
    },
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

// 搜索关键词
const searchKeyword = ref('')

// 价格基准显示文本映射
const priceBaseMap: Record<string, string> = {
    'jita_sell': 'Jita 出单',
    'jita_mid': 'Jita 中间',
    'jita_buy': 'Jita 收单'
}

const priceBaseText = priceBaseMap[props.config.price_base] || props.config.price_base

// 过滤后的资产列表
const filteredAssetView = computed(() => {
    let result = [...props.assetView]
    
    // 如果有搜索关键词，先进行过滤
    if (searchKeyword.value.trim()) {
        const keyword = searchKeyword.value.toLowerCase().trim()
        result = result.filter(asset => {
            const nameZh = (asset.type_name_zh || '').toLowerCase()
            const nameEn = asset.type_name.toLowerCase()
            return nameZh.includes(keyword) || nameEn.includes(keyword)
        })
    }
    
    // 根据价格从大到小排序
    return result.sort((a, b) => b.price - a.price)
})
</script>

<template>
    <div v-loading="loading" class="sell-view-content">
        <div class="sell-view-container">
            <!-- 配置信息卡片 -->
            <KCard class="config-card">
                <div class="config-header">
                    <el-icon class="config-icon"><Setting /></el-icon>
                    <span class="config-title">价格配置</span>
                </div>
                <div class="config-content">
                    <div class="config-item">
                        <span class="config-label">价格基准：</span>
                        <el-tag type="primary" size="large">{{ priceBaseText }}</el-tag>
                    </div>
                    <div class="config-item">
                        <span class="config-label">百分比：</span>
                        <el-tag type="success" size="large">{{ (config.percent * 100).toFixed(0) }}%</el-tag>
                    </div>
                </div>
            </KCard>

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
                hint="先在资产列表刷新一次角色资产，再回来查看可售价格"
            />
            <template v-else>
                <!-- 搜索框 -->
                <div class="search-container">
                    <el-input
                        v-model="searchKeyword"
                        placeholder="搜索资产名称（支持中文/英文）"
                        clearable
                        class="search-input"
                    >
                        <template #prefix>
                            <el-icon><Search /></el-icon>
                        </template>
                    </el-input>
                </div>

                <!-- 资产列表 -->
                <div class="asset-grid">
                <KCard 
                    v-for="asset in filteredAssetView" 
                    :key="asset.type_id" 
                    class="asset-tile"
                    padding="none"
                >
                    <div class="asset-item-content">
                        <!-- 图标容器 -->
                        <div class="asset-icon-container">
                            <img 
                                :src="`https://imageserver.eveonline.com/Type/${asset.type_id}_64.png`" 
                                :alt="asset.type_name"
                                class="asset-icon" loading="lazy"
                            />
                            <!-- 可售标记 -->
                            <!-- <div class="asset-sellable-badge">S</div> -->
                        </div>
                        <!-- 信息区域 -->
                        <div class="asset-info-section">
                            <!-- 第一行：中文名 | 个数 -->
                            <div class="asset-top-row">
                                <div class="asset-name-zh">{{ asset.type_name_zh || asset.type_name }}</div>
                                <KStat
                                    label="数量"
                                    :value="asset.quantity"
                                    unit="个"
                                    tone="success"
                                />
                            </div>
                            <!-- 第二行：英文名 -->
                            <div class="asset-name-en">{{ asset.type_name }}</div>
                            <!-- 第三行：价格 -->
                            <div class="asset-price-display">
                                <span class="price-value">{{ asset.price.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</span>
                                <span class="price-unit"> ISK</span>
                            </div>
                        </div>
                    </div>
                </KCard>
            </div>
        </template>
    </div>
</div>
</template>

<style scoped>
.sell-view-content {
    min-height: 400px;
}

.sell-view-container {
    display: flex;
    flex-direction: column;
    gap: 20px;
}

/* 配置卡片样式 */
.config-card {
    background: linear-gradient(
        135deg,
        color-mix(in srgb, var(--k-color-primary) 18%, var(--k-color-surface-soft)) 0%,
        color-mix(in srgb, var(--k-color-primary) 30%, var(--k-color-surface)) 100%
    );
    border: 1px solid var(--k-color-border-subtle);
    color: var(--k-color-text);
}

.config-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
}

.config-icon {
    font-size: 20px;
}

.config-title {
    font-size: 18px;
    font-weight: 600;
}

.config-content {
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
}

.config-item {
    display: flex;
    align-items: center;
    gap: 8px;
}

.config-label {
    font-size: 14px;
    color: var(--k-color-text-secondary);
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
    color: var(--k-color-primary);
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

/* 搜索框样式 */
.search-container {
    padding: 0 8px;
}

.search-input {
    width: 100%;
    max-width: 500px;
}

.search-input :deep(.el-input__wrapper) {
    border-radius: 8px;
    box-shadow: var(--k-shadow-sm);
    transition: all 0.3s ease;
}

.search-input :deep(.el-input__wrapper:hover) {
    box-shadow: 0 4px 12px color-mix(in srgb, var(--k-color-primary) 20%, transparent);
}

.search-input :deep(.el-input__wrapper.is-focus) {
    box-shadow: 0 4px 12px color-mix(in srgb, var(--k-color-primary) 30%, transparent);
}

/* 资产网格 */
.asset-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 16px;
    padding: 8px;
}

/* 资产卡片 - EVE风格 */
.asset-tile {
    width: 300px;
    height: 100px;
    transition: all 0.3s ease;
    background: var(--k-color-surface);
    border: 1px solid var(--k-color-border-subtle);
    border-radius: 4px 0 0 4px;
    overflow: hidden;
    position: relative;
    /* EVE风格切角效果：右上角和左下角切角 */
    clip-path: polygon(
        0 0,
        calc(100% - 8px) 0,
        100% 8px,
        100% 100%,
        8px 100%,
        0 calc(100% - 8px)
    );
}

.asset-tile:hover {
    transform: translateY(-2px);
    box-shadow: var(--k-shadow-sm);
    border-color: var(--k-color-border);
    background: color-mix(in srgb, var(--k-color-primary) 8%, var(--k-color-surface-soft));
}

.asset-tile :deep(.k-card__body) {
    padding: 6px 8px;
    height: 100%;
}

.asset-item-content {
    display: flex;
    flex-direction: row;
    gap: 10px;
    height: 100%;
    align-items: center;
}

/* 图标容器 */
.asset-icon-container {
    position: relative;
    width: 64px;
    height: 64px;
    flex-shrink: 0;
    border: 1px solid var(--k-color-border-subtle);
    background: var(--k-color-surface-soft);
    display: flex;
    align-items: center;
    justify-content: center;
}

.asset-icon {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
}

/* 可售标记 */
.asset-sellable-badge {
    position: absolute;
    top: -2px;
    left: -2px;
    width: 16px;
    height: 16px;
    background: linear-gradient(135deg, var(--k-color-warning) 0%, color-mix(in srgb, var(--k-color-warning) 72%, var(--k-color-shade)) 100%);
    clip-path: polygon(0 0, 100% 0, 0 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    color: var(--k-color-on-warning);
    z-index: 2;
    line-height: 1;
    padding: 1px 0 0 1px;
}

/* 信息区域 */
.asset-info-section {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    height: 100%;
    min-width: 0;
    padding: 4px 2px 4px 0;
    overflow: hidden;
}

/* 第一行：中文名 | 个数 */
.asset-top-row {
    display: flex;
    align-items: flex-start;
    justify-content: flex-start;
    gap: 8px;
    margin-bottom: 4px;
    min-width: 0;
    width: 100%;
}

.asset-name-zh {
    flex: 0 1 auto;
    font-size: 15px;
    font-weight: 700;
    color: var(--k-color-text);
    line-height: 1.3;
    word-break: break-word;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    min-width: 0;
    max-width: calc(100% - 50px);
}

/* 个数显示由 KStat 承担（等宽数字 + 语义色） */

/* 第二行：英文名 */
.asset-name-en {
    font-size: 11px;
    color: var(--k-color-text-secondary);
    line-height: 1.3;
    word-break: break-word;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 1;
    line-clamp: 1;
    -webkit-box-orient: vertical;
    margin-bottom: 4px;
}

/* 第三行：价格 */
.asset-price-display {
    display: flex;
    align-items: baseline;
    margin-top: 4px;
}

.price-value {
    font-size: 13px;
    font-weight: 700;
    color: var(--k-color-primary);
    line-height: 1.2;
    white-space: nowrap;
}

.price-unit {
    font-size: 11px;
    color: var(--k-color-text-tertiary);
    margin-left: 2px;
    white-space: nowrap;
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
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 12px;
    }

    .asset-tile {
        width: 100%;
        max-width: 220px;
    }

    .config-content {
        flex-direction: column;
        gap: 12px;
    }
}

@media (max-width: 480px) {
    .asset-grid {
        grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        gap: 10px;
    }

    .asset-tile {
        width: 100%;
        max-width: 220px;
        height: 90px;
    }

    .asset-icon-container {
        width: 56px;
        height: 56px;
    }

    .asset-name-zh {
        font-size: 13px;
    }

    .asset-name-en {
        font-size: 11px;
    }

    .price-value {
        font-size: 12px;
    }

    .price-unit {
        font-size: 11px;
    }
}

/* 次要按钮 hover 保持品牌色（token 混合，无需 !important） */
.sell-view-container :deep(.el-button:not(.el-button--primary):hover) {
    color: var(--k-color-primary);
    background: color-mix(in srgb, var(--k-color-primary) 10%, var(--k-color-surface-soft));
    border-color: color-mix(in srgb, var(--k-color-primary) 35%, var(--k-color-border));
}
</style>
