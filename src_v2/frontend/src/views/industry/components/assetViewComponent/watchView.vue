<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Setting, DocumentCopy } from '@element-plus/icons-vue'
import { http } from '@/http'
import { ElMessage } from 'element-plus'

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
    sid: string,
    view_type: string,
    config: {
        watch_list?: {
            [type_id: number]: {
                quantity: number
            }
        }
    }
}

const props = defineProps<Props>()

const AssetViewSort = computed(() => {
    return props.assetView.sort((a, b) => {
        return b.type_id - a.type_id
    })
})

const setAllTargetLineDialogVisible = ref(false)
const setAllTargetLineForm = ref({
    targetLine: 0
})

// 取整百分比（默认25%）
const roundPercentage = ref(25)
// 位数取整（默认1，即不取整）
const roundDigit = ref(1)

// 将位数取整值调整为10的幂次方（1, 10, 100, 1000等）
const adjustRoundDigit = (value: number): number => {
    if (value <= 1) return 1
    // 计算最接近的10的幂次方
    const power = Math.round(Math.log10(value))
    return Math.pow(10, power)
}

// 获取下一个10的幂次方
const getNextPowerOf10 = (value: number): number => {
    if (value < 1) return 1
    const currentPower = Math.floor(Math.log10(value))
    return Math.pow(10, currentPower + 1)
}

// 获取上一个10的幂次方
const getPrevPowerOf10 = (value: number): number => {
    if (value <= 1) return 1
    const currentPower = Math.floor(Math.log10(value))
    if (currentPower <= 0) return 1
    return Math.pow(10, currentPower)
}

// 保存上一次的值，用于判断变化方向
const prevRoundDigit = ref(1)

// 监听位数取整值变化，自动调整为10的幂次方
watch(roundDigit, (newValue, oldValue) => {
    if (newValue === null || newValue === undefined) {
        roundDigit.value = 1
        prevRoundDigit.value = 1
        return
    }
    
    // 如果已经是10的幂次方，直接返回
    const logValue = Math.log10(newValue)
    if (Math.abs(logValue - Math.round(logValue)) < 0.0001) {
        prevRoundDigit.value = newValue
        return
    }
    
    // 判断变化方向
    let adjusted: number
    if (newValue > prevRoundDigit.value) {
        // 向上变化，取下一个10的幂次方
        adjusted = getNextPowerOf10(newValue)
    } else if (newValue < prevRoundDigit.value) {
        // 向下变化，取上一个10的幂次方
        adjusted = getPrevPowerOf10(newValue)
    } else {
        // 值相同，取最接近的10的幂次方
        adjusted = adjustRoundDigit(newValue)
    }
    
    if (adjusted !== newValue) {
        roundDigit.value = adjusted
        prevRoundDigit.value = adjusted
    } else {
        prevRoundDigit.value = newValue
    }
}, { immediate: false })

const setAllTargetLine = () => {
    setAllTargetLineDialogVisible.value = true
    setAllTargetLineForm.value.targetLine = 100
}

// 单个物品填充线设置
const setSingleTargetLineDialogVisible = ref(false)
const currentAsset = ref<AssetItem | null>(null)
const setSingleTargetLineForm = ref({
    targetLine: 0
})

const setSingleTargetLine = (asset: AssetItem) => {
    currentAsset.value = asset
    // 初始化 watch_list 如果不存在
    if (!props.config.watch_list) {
        props.config.watch_list = {}
    }
    // 使用当前 watch_list 中的值，如果没有则使用当前数量
    setSingleTargetLineForm.value.targetLine = props.config.watch_list[asset.type_id]?.quantity || asset.quantity || 100
    setSingleTargetLineDialogVisible.value = true
}

const handleSetSingleTargetLine = async () => {
    if (!currentAsset.value) return

    // 初始化 watch_list 如果不存在
    if (!props.config.watch_list) {
        props.config.watch_list = {}
    }

    // 为单个资产设置目标线
    props.config.watch_list[currentAsset.value.type_id] = {
        quantity: setSingleTargetLineForm.value.targetLine
    }

    const res = await http.post('/EVE/asset/saveAssetViewConfig', {
        sid: props.sid,
        config: props.config
    })
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    ElMessage.success(data.message || '保存成功')

    setSingleTargetLineDialogVisible.value = false
    currentAsset.value = null
}

const handleSetAllTargetLine = async () => {
    console.log('handleSetAllTargetLine', setAllTargetLineForm.value.targetLine)

    // 初始化 watch_list 如果不存在
    if (!props.config.watch_list) {
        props.config.watch_list = {}
    }

    // 为所有资产设置目标线
    props.assetView.forEach(asset => {
        props.config.watch_list![asset.type_id] = {
            quantity: setAllTargetLineForm.value.targetLine
        }
    })

    const res = await http.post('/EVE/asset/saveAssetViewConfig', {
        sid: props.sid,
        config: props.config
    })
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    ElMessage.success(data.message || '保存成功')

    setAllTargetLineDialogVisible.value = false
}

// 计算进度百分比
const getProgressPercentage = (asset: AssetItem): number => {
    const targetQuantity = props.config.watch_list?.[asset.type_id]?.quantity || 0
    if (targetQuantity === 0) return 0
    return Math.min(Math.floor((asset.quantity / targetQuantity) * 100), 100)
}

// 获取进度条颜色
const getProgressColor = (asset: AssetItem): string => {
    const percentage = getProgressPercentage(asset)
    if (percentage >= 75) {
        return '#67c23a' // 绿色 - 已达标
    } else if (percentage >= 50) {
        return '#e6a23c' // 橙色 - 接近目标
    } else if (percentage >= 25) {
        return '#f56c6c' // 橙红色 - 接近不足
    } else {
        return '#ff4d4f' // 红色 - 严重不足
    }
}

// 计算补充数量：根据填充率向上取整到自定义百分比，然后进行位数取整
const calculateReplenishQuantity = (asset: AssetItem): number => {
    const targetQuantity = props.config.watch_list?.[asset.type_id]?.quantity || 0
    if (targetQuantity === 0) return 0
    
    const percentage = getProgressPercentage(asset)
    // 如果填充率 >= 100%，不需要补充
    if (percentage >= 100) return 0
    
    // 需要补充的百分比 = 100 - 填充率
    const replenishPercentage = 100 - percentage
    // 向上取整到自定义百分比的倍数
    const roundedPercentage = Math.ceil(replenishPercentage / roundPercentage.value) * roundPercentage.value
    // 计算补充数量（百分比取整后）
    let replenishQuantity = Math.ceil(targetQuantity * (roundedPercentage / 100))
    
    // 进行位数取整（向上取整到指定位数的倍数）
    if (roundDigit.value > 1) {
        replenishQuantity = Math.ceil(replenishQuantity / roundDigit.value) * roundDigit.value
    }
    
    return replenishQuantity
}

// 生成采购清单文本：格式为"中文名 英文名 数量"
const generatePurchaseList = (assets: AssetItem[]): string => {
    const lines: string[] = []
    
    assets.forEach(asset => {
        const replenishQuantity = calculateReplenishQuantity(asset)
        // 只包含需要补充的物品（数量 > 0）
        if (replenishQuantity > 0) {
            const chineseName = asset.type_name_zh || asset.type_name
            const englishName = asset.type_name
            lines.push(`${chineseName} ${englishName} ${replenishQuantity}`)
        }
    })
    
    return lines.join('\n')
}

// 复制单个物品的采购清单
const copySingleItemPurchaseList = async (asset: AssetItem) => {
    const replenishQuantity = calculateReplenishQuantity(asset)
    
    if (replenishQuantity === 0) {
        ElMessage.warning('该物品已满足目标数量，无需采购')
        return
    }
    
    const chineseName = asset.type_name_zh || asset.type_name
    const englishName = asset.type_name
    const text = `${chineseName} ${englishName} ${replenishQuantity}`
    
    try {
        await navigator.clipboard.writeText(text)
        ElMessage.success('已复制到剪贴板')
    } catch (error) {
        ElMessage.error('复制失败，请手动复制')
    }
}

// 复制所有物品的采购清单
const copyAllPurchaseList = async () => {
    const text = generatePurchaseList(props.assetView)
    
    if (!text) {
        ElMessage.warning('没有需要采购的物品')
        return
    }
    
    try {
        await navigator.clipboard.writeText(text)
        ElMessage.success('已复制采购清单到剪贴板')
    } catch (error) {
        ElMessage.error('复制失败，请手动复制')
    }
}

</script>


<template>
    <div v-loading="loading" class="watch-view-content">
        <div v-if="!loading && assetView.length === 0" class="empty-state">
            <el-empty description="暂无数据" />
        </div>
        <div v-else class="watch-view-container">
            <!-- 顶部操作区域 -->
            <div class="action-bar">
                <el-button 
                    type="primary" 
                    :icon="Setting" 
                    @click="setAllTargetLine"
                    class="set-all-button"
                >
                    设置全体目标线
                </el-button>
                <el-button 
                    type="success" 
                    :icon="DocumentCopy" 
                    @click="copyAllPurchaseList"
                    class="copy-all-button"
                >
                    复制采购清单
                </el-button>
                <div class="round-percentage-input">
                    <span class="input-label">取整百分比:</span>
                    <el-input-number 
                        v-model="roundPercentage" 
                        :min="1" 
                        :max="100" 
                        :step="5"
                        :precision="0"
                        size="default"
                        class="percentage-input"
                    />
                    <span class="input-suffix">%</span>
                </div>
                <div class="round-digit-input">
                    <span class="input-label">位数取整:</span>
                    <el-input-number 
                        v-model="roundDigit" 
                        :min="1" 
                        :step="1"
                        :precision="0"
                        size="default"
                        class="digit-input"
                        :controls-position="'right'"
                    />
                </div>
            </div>
        
            <!-- 资产网格 -->
            <div class="asset-grid">
                <el-card 
                    v-for="asset in AssetViewSort" 
                    :key="asset.type_id" 
                    class="asset-item-card"
                    shadow="hover"
                >
                    <!-- 设置按钮 -->
                    <el-button 
                        type="primary" 
                        :icon="Setting" 
                        circle 
                        size="small"
                        class="setting-button"
                        @click="setSingleTargetLine(asset)"
                    />
                    <!-- 复制按钮 -->
                    <el-button 
                        type="success" 
                        :icon="DocumentCopy" 
                        circle 
                        size="small"
                        class="copy-button"
                        @click="copySingleItemPurchaseList(asset)"
                    />
                    
                    <!-- 卡片内容 -->
                    <div class="asset-item-content">
                        <!-- 进度条和图标 -->
                        <div class="progress-container">
                            <el-progress 
                                type="circle" 
                                :percentage="getProgressPercentage(asset)" 
                                :color="getProgressColor(asset)"
                                :stroke-width="8"
                                :width="130"
                                :show-text="true"
                                class="asset-progress"
                            >
                                <template #default>
                                    <div class="progress-inner">
                                        <el-avatar 
                                            :size="90" 
                                            :src="`https://imageserver.eveonline.com/Type/${asset.type_id}_64.png`" 
                                            shape="circle"
                                            class="asset-avatar"
                                        />
                                    </div>
                                </template>
                            </el-progress>
                            <div class="progress-text">
                                <div class="progress-percentage">{{ getProgressPercentage(asset) }}%</div>
                                <div class="progress-label">填充率</div>
                            </div>
                        </div>
                        
                        <!-- 资产信息 -->
                        <div class="asset-info">
                            <div class="asset-name-zh">{{ asset.type_name_zh || asset.type_name }}</div>
                            <div class="asset-name-en">{{ asset.type_name }}</div>
                            <div class="asset-quantity-section">
                                <el-tag type="success" class="asset-quantity-tag" size="large">
                                    {{ asset.quantity }} / {{ props.config.watch_list?.[asset.type_id]?.quantity || '-' }}
                                </el-tag>
                            </div>
                        </div>
                    </div>
                </el-card>
            </div>
        </div>
    </div>

    <!-- 设置全体目标线对话框 -->
    <el-dialog v-model="setAllTargetLineDialogVisible" title="设置全体目标线" width="500px">
        <el-form :model="setAllTargetLineForm" label-width="120px">
            <el-form-item label="目标线">
                <el-input-number v-model="setAllTargetLineForm.targetLine" placeholder="请输入目标线" :min="0" />
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="setAllTargetLineDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="handleSetAllTargetLine">确定</el-button>
        </template>
    </el-dialog>

    <!-- 设置单个目标线对话框 -->
    <el-dialog v-model="setSingleTargetLineDialogVisible" :title="`设置填充线 - ${currentAsset?.type_name_zh || currentAsset?.type_name || ''}`" width="500px">
        <el-form :model="setSingleTargetLineForm" label-width="120px">
            <el-form-item label="目标线">
                <el-input-number v-model="setSingleTargetLineForm.targetLine" placeholder="请输入目标线" :min="0" />
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="setSingleTargetLineDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="handleSetSingleTargetLine">确定</el-button>
        </template>
    </el-dialog>
</template>

<style scoped>
/* 主容器 */
.watch-view-content {
    min-height: 400px;
}

.empty-state {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 400px;
}

.watch-view-container {
    display: flex;
    flex-direction: column;
    gap: 20px;
}

/* 顶部操作栏 */
.action-bar {
    padding: 0 8px;
    display: flex;
    justify-content: flex-start;
}

.set-all-button {
    font-size: 14px;
    padding: 10px 20px;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
    transition: all 0.3s ease;
}

.set-all-button:hover {
    box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
    transform: translateY(-1px);
}

.copy-all-button {
    font-size: 14px;
    padding: 10px 20px;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(103, 194, 58, 0.2);
    transition: all 0.3s ease;
    margin-left: 12px;
}

.copy-all-button:hover {
    box-shadow: 0 4px 12px rgba(103, 194, 58, 0.3);
    transform: translateY(-1px);
}

/* 取整百分比输入框 */
.round-percentage-input {
    display: flex;
    align-items: center;
    margin-left: 16px;
    gap: 8px;
}

/* 位数取整输入框 */
.round-digit-input {
    display: flex;
    align-items: center;
    margin-left: 16px;
    gap: 8px;
}

.input-label {
    font-size: 14px;
    color: #606266;
    white-space: nowrap;
}

.percentage-input {
    width: 100px;
}

.digit-input {
    width: 120px;
}

.input-suffix {
    font-size: 14px;
    color: #909399;
    white-space: nowrap;
}

/* 资产网格 */
.asset-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 20px;
    padding: 8px;
}

/* 资产卡片 */
.asset-item-card {
    position: relative;
    transition: all 0.3s ease;
    background: white;
    border-radius: 12px;
    overflow: visible;
}

.asset-item-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

/* 设置按钮 */
.setting-button {
    position: absolute;
    top: 12px;
    right: 12px;
    z-index: 10;
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.3);
    transition: all 0.3s ease;
}

.setting-button:hover {
    transform: scale(1.1);
    box-shadow: 0 4px 12px rgba(64, 158, 255, 0.4);
}

/* 复制按钮 */
.copy-button {
    position: absolute;
    top: 12px;
    right: 56px;
    z-index: 10;
    box-shadow: 0 2px 8px rgba(103, 194, 58, 0.3);
    transition: all 0.3s ease;
}

.copy-button:hover {
    transform: scale(1.1);
    box-shadow: 0 4px 12px rgba(103, 194, 58, 0.4);
}

/* 卡片内容 */
.asset-item-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 6px 6px;
    gap: 10px;
}

/* 进度条容器 */
.progress-container {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 4px 0;
}

.asset-progress {
    margin-bottom: 4px;
}

.progress-inner {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
}

.asset-avatar {
    border: 2px solid #f0f0f0;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
}

.progress-text {
    text-align: center;
    pointer-events: none;
    margin-top: 2px;
}

.progress-percentage {
    font-size: 14px;
    font-weight: 700;
    color: #303133;
    line-height: 1.2;
}

.progress-label {
    font-size: 10px;
    color: #909399;
    margin-top: 1px;
}

/* 资产信息 */
.asset-info {
    width: 100%;
    text-align: center;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.asset-name-zh {
    font-size: 14px;
    font-weight: 600;
    color: #303133;
    word-break: break-word;
    line-height: 1.3;
}

.asset-name-en {
    font-size: 11px;
    color: #909399;
    word-break: break-word;
    line-height: 1.2;
}

.asset-quantity-section {
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 2px;
}

.asset-quantity-tag {
    font-size: 13px;
    font-weight: 600;
    padding: 4px 12px;
    box-shadow: 0 2px 4px rgba(103, 194, 58, 0.2);
}

/* 响应式设计 */
@media (max-width: 768px) {
    .action-bar {
        flex-wrap: wrap;
        gap: 12px;
    }

    .round-percentage-input,
    .round-digit-input {
        margin-left: 0;
        width: 100%;
        justify-content: flex-start;
    }

    .asset-grid {
        grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        gap: 16px;
    }

    .asset-item-content {
        padding: 12px 10px;
        gap: 8px;
    }

    .asset-progress {
        width: 100px !important;
    }

    .asset-progress :deep(.el-progress-circle) {
        width: 100px !important;
        height: 100px !important;
    }

    .asset-avatar {
        width: 50px !important;
        height: 50px !important;
    }

    .progress-percentage {
        font-size: 14px;
    }

    .asset-name-zh {
        font-size: 14px;
    }

    .asset-name-en {
        font-size: 11px;
    }
}

@media (max-width: 480px) {
    .asset-grid {
        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
        gap: 12px;
    }

    .asset-item-content {
        padding: 10px 8px;
        gap: 8px;
    }

    .asset-progress {
        width: 90px !important;
    }

    .asset-progress :deep(.el-progress-circle) {
        width: 90px !important;
        height: 90px !important;
    }

    .asset-avatar {
        width: 45px !important;
        height: 45px !important;
    }

    .progress-percentage {
        font-size: 12px;
    }

    .progress-label {
        font-size: 10px;
    }

    .asset-name-zh {
        font-size: 13px;
    }

    .asset-name-en {
        font-size: 10px;
    }

    .asset-quantity-tag {
        font-size: 13px;
        padding: 4px 10px;
    }

    .setting-button {
        top: 8px;
        right: 8px;
    }

    .copy-button {
        top: 8px;
        right: 52px;
    }
}
</style>