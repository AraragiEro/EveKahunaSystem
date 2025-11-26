<script setup lang="ts">
import { ref, computed } from 'vue'
import { Setting, Search } from '@element-plus/icons-vue'

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
    }
}

const props = defineProps<Props>()

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
    if (!searchKeyword.value.trim()) {
        return props.assetView
    }
    const keyword = searchKeyword.value.toLowerCase().trim()
    return props.assetView.filter(asset => {
        const nameZh = (asset.type_name_zh || '').toLowerCase()
        const nameEn = asset.type_name.toLowerCase()
        return nameZh.includes(keyword) || nameEn.includes(keyword)
    })
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
                        <!-- 图片容器 -->
                        <div class="asset-image-container">
                            <img 
                                :src="`https://imageserver.eveonline.com/Type/${asset.type_id}_256.png`" 
                                :alt="asset.type_name"
                                class="asset-image"
                            />
                            <!-- 渐变遮罩 -->
                            <div class="asset-gradient-overlay"></div>
                            <!-- 文字信息层 -->
                            <div class="asset-info-overlay">
                                <div class="asset-name-section">
                                    <div class="asset-name-zh">{{ asset.type_name_zh || asset.type_name }}</div>
                                    <div class="asset-name-en">{{ asset.type_name }}</div>
                                </div>
                                <div class="asset-quantity-section">
                                    <el-tag type="success" class="asset-quantity" size="large">
                                        {{ asset.quantity }} 个
                                    </el-tag>
                                </div>
                            </div>
                        </div>
                        <!-- 价格区域 -->
                        <div class="asset-price">
                            <div class="price-label">单价</div>
                            <el-statistic 
                                :value="asset.price" 
                                :precision="2" 
                                :suffix="' ISK'"
                                class="price-statistic"
                            />
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
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
    padding: 8px;
}

/* 资产卡片 */
.asset-item-card {
    transition: all 0.3s ease;
    background: white;
}

.asset-item-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.asset-item-card:hover .asset-image-container {
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
}

.asset-item-content {
    display: flex;
    flex-direction: column;
    gap: 0;
}

/* 图片容器 */
.asset-image-container {
    position: relative;
    width: 100%;
    aspect-ratio: 1 / 1;
    border-radius: 12px;
    overflow: hidden;
    background: #f5f7fa;
}

.asset-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}

/* 渐变遮罩 */
.asset-gradient-overlay {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 33.33%;
    background: linear-gradient(to top, 
        rgba(0, 0, 0, 0.85) 0%, 
        rgba(0, 0, 0, 0.65) 25%, 
        rgba(0, 0, 0, 0.4) 50%, 
        rgba(0, 0, 0, 0.15) 75%, 
        transparent 100%
    );
    pointer-events: none;
    z-index: 1;
}

/* 文字信息层 */
.asset-info-overlay {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 33.33%;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    padding: 12px 16px;
    z-index: 2;
}

.asset-name-section {
    flex: 1;
    text-align: left;
    color: white;
    min-width: 0;
}

.asset-name-zh {
    font-size: 20px;
    font-weight: 600;
    color: white;
    margin-bottom: 2px;
    word-break: break-word;
    line-height: 1.3;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}

.asset-name-en {
    font-size: 14px;
    color: rgba(255, 255, 255, 0.9);
    word-break: break-word;
    line-height: 1.3;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}

.asset-quantity-section {
    flex-shrink: 0;
    margin-left: 12px;
    display: flex;
    align-items: flex-end;
}

.asset-quantity {
    font-size: 16px;
    font-weight: 600;
    padding: 4px 10px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
}

/* 价格显示 */
.asset-price {
    width: 100%;
    padding: 12px 16px;
    text-align: center;
    min-height: 60px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    background: #fafafa;
}

.price-label {
    font-size: 12px;
    color: #909399;
    margin-bottom: 4px;
}

.price-statistic {
    margin-top: 4px;
}

.price-statistic :deep(.el-statistic__number) {
    font-size: 18px;
    font-weight: 600;
    color: #409eff;
}

.price-statistic :deep(.el-statistic__suffix) {
    font-size: 14px;
    color: #909399;
    margin-left: 4px;
}

/* 响应式设计 */
@media (max-width: 768px) {
    .asset-grid {
        grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        gap: 12px;
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
        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
        gap: 8px;
    }

    .asset-image-container {
        border-radius: 8px;
    }

    .asset-info-overlay {
        padding: 8px 12px;
    }

    .asset-name-zh {
        font-size: 12px;
    }

    .asset-name-en {
        font-size: 10px;
    }

    .asset-quantity {
        font-size: 11px;
        padding: 3px 8px;
    }

    .asset-price {
        padding: 8px 12px;
        min-height: 50px;
    }

    .price-statistic :deep(.el-statistic__number) {
        font-size: 16px;
    }
}
</style>