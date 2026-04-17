<script setup lang="ts">
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
        <div v-if="!loading && assetView.length === 0" class="empty-state">
            <el-empty description="暂无数据" />
        </div>
        <div v-else class="sell-view-container">
            <!-- 配置信息卡片 -->
            <el-card class="config-card" shadow="hover">
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
            </el-card>

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
                <el-card 
                    v-for="asset in filteredAssetView" 
                    :key="asset.type_id" 
                    class="asset-item-card"
                    shadow="hover"
                >
                    <div class="asset-item-content">
                        <!-- 图标容器 -->
                        <div class="asset-icon-container">
                            <img 
                                :src="`https://imageserver.eveonline.com/Type/${asset.type_id}_64.png`" 
                                :alt="asset.type_name"
                                class="asset-icon"
                            />
                            <!-- 可售标记 -->
                            <!-- <div class="asset-sellable-badge">S</div> -->
                        </div>
                        <!-- 信息区域 -->
                        <div class="asset-info-section">
                            <!-- 第一行：中文名 | 个数 -->
                            <div class="asset-top-row">
                                <div class="asset-name-zh">{{ asset.type_name_zh || asset.type_name }}</div>
                                <div class="asset-quantity-display">
                                    <div class="quantity-number">{{ asset.quantity }}</div>
                                    <div class="quantity-unit">个</div>
                                </div>
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
                </el-card>
            </div>
        </div>
    </div>
</template>

<style scoped>
.sell-view-content {
    min-height: 400px;
}

.empty-state {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 400px;
}

.sell-view-container {
    display: flex;
    flex-direction: column;
    gap: 20px;
}

/* 配置卡片样式 */
.config-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
    color: white;
}

.config-card :deep(.el-card__body) {
    padding: 20px;
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
    opacity: 0.9;
}

.config-item :deep(.el-tag) {
    font-size: 14px;
    padding: 6px 12px;
    background-color: rgba(255, 255, 255, 0.2);
    border-color: rgba(255, 255, 255, 0.3);
    color: white;
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
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    transition: all 0.3s ease;
}

.search-input :deep(.el-input__wrapper:hover) {
    box-shadow: 0 4px 12px rgba(64, 158, 255, 0.2);
}

.search-input :deep(.el-input__wrapper.is-focus) {
    box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
}

/* 资产网格 */
.asset-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 16px;
    padding: 8px;
}

/* 资产卡片 - EVE风格 */
.asset-item-card {
    width: 300px;
    height: 100px;
    transition: all 0.3s ease;
    background: #2D3234;
    border: none;
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

.asset-item-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    background: #353A3D;
}

.asset-item-card :deep(.el-card__body) {
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
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(0, 0, 0, 0.3);
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
    background: linear-gradient(135deg, #ffa500 0%, #ff8c00 100%);
    clip-path: polygon(0 0, 100% 0, 0 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: 700;
    color: #000;
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
    color: #ffffff;
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

/* 个数显示 - 两行，显眼加粗现代化字体 */
.asset-quantity-display {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    flex-shrink: 0;
    line-height: 1;
}

.quantity-number {
    font-size: 18px;
    font-weight: 800;
    color: #67c23a;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;
    letter-spacing: -0.5px;
    line-height: 1.1;
}

.quantity-unit {
    font-size: 10px;
    font-weight: 600;
    color: rgba(103, 194, 58, 0.8);
    margin-top: 2px;
    line-height: 1;
}

/* 第二行：英文名 */
.asset-name-en {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.7);
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
    color: #409eff;
    line-height: 1.2;
    white-space: nowrap;
}

.price-unit {
    font-size: 10px;
    color: rgba(255, 255, 255, 0.6);
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

    .asset-item-card {
        width: 100%;
        max-width: 220px;
    }

    .config-content {
        flex-direction: column;
        gap: 12px;
    }

    .config-card :deep(.el-card__body) {
        padding: 16px;
    }
}

@media (max-width: 480px) {
    .asset-grid {
        grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        gap: 10px;
    }

    .asset-item-card {
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
        font-size: 10px;
    }

    .quantity-number {
        font-size: 16px;
    }

    .quantity-unit {
        font-size: 9px;
    }

    .price-value {
        font-size: 12px;
    }

    .price-unit {
        font-size: 9px;
    }
}

/* Theme override */
.sell-view-content,
.sell-view-container,
.config-card,
.toolbar,
.search-container,
.asset-grid,
.asset-item-card,
.asset-item-content,
.asset-info-section {
    border-color: var(--k-color-border) !important;
}

.sell-view-content,
.sell-view-container,
.toolbar,
.search-container,
.asset-item-card {
    background: var(--k-color-surface) !important;
    color: var(--k-color-text) !important;
}

.asset-item-card {
    box-shadow: var(--k-shadow-sm) !important;
}

.asset-item-card:hover {
    box-shadow: var(--k-shadow-md) !important;
    background: color-mix(in srgb, var(--k-color-primary) 8%, var(--k-color-surface-soft)) !important;
}

.config-card {
    background: linear-gradient(
        135deg,
        color-mix(in srgb, var(--k-color-primary) 18%, var(--k-color-surface-soft)) 0%,
        color-mix(in srgb, var(--k-color-primary) 30%, var(--k-color-surface)) 100%
    ) !important;
    color: var(--k-color-text) !important;
}

.config-label,
.time-label,
.asset-name-en,
.price-unit {
    color: var(--k-color-text-secondary) !important;
}

.time-value,
.price-value {
    color: var(--k-color-primary) !important;
}

.asset-name-zh {
    color: var(--k-color-text) !important;
}

.asset-sellable-badge {
    background: linear-gradient(
        135deg,
        color-mix(in srgb, var(--k-color-warning) 90%, #0000) 0%,
        color-mix(in srgb, var(--k-color-warning) 65%, #0000) 100%
    ) !important;
}

.quantity-number {
    color: var(--k-color-success) !important;
}

.quantity-unit {
    color: color-mix(in srgb, var(--k-color-success) 72%, var(--k-color-text-secondary)) !important;
}

.sell-view-container :deep(.el-input__wrapper),
.sell-view-container :deep(.el-card),
.sell-view-container :deep(.el-button),
.sell-view-container :deep(.el-tag) {
    background: var(--k-color-surface) !important;
    border-color: var(--k-color-border) !important;
    color: var(--k-color-text) !important;
}

.sell-view-container :deep(.el-button:not(.el-button--primary):hover) {
    color: var(--k-color-primary) !important;
    background: color-mix(in srgb, var(--k-color-primary) 10%, var(--k-color-surface-soft)) !important;
    border-color: color-mix(in srgb, var(--k-color-primary) 35%, var(--k-color-border)) !important;
}
</style>
