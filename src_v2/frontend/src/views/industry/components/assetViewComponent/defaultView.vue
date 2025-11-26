<script setup lang="ts">
interface AssetItem {
    type_id: number
    type_name: string
    type_name_zh?: string
    quantity: number
}

interface Props {
    loading: boolean
    assetView: AssetItem[]
}

defineProps<Props>()
</script>

<template>
    <div v-loading="loading" class="asset-view-dialog-content">
        <div v-if="!loading && assetView.length === 0" class="empty-state">
            <el-empty description="暂无数据" />
        </div>
        <div v-else class="asset-grid">
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
    .asset-grid {
        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
        gap: 12px;
    }
}
</style>

