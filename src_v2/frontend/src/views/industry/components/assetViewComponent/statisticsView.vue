<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { ElMessage } from 'element-plus'
import { ArrowUp, ArrowDown, Refresh } from '@element-plus/icons-vue'

// 资产数据结构
interface AssetItem {
    type_id: number
    type_name: string
    type_name_zh: string
    quantity: number
    price: number
    class_type: string
}

interface ContainerData {
    container_id: number
    name: string
    assets: Record<number, AssetItem>
}

interface Props {
    loading: boolean
    assetView: Record<number, ContainerData>
    sid: string
    view_type: string
    config: any
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

// 格式化数字
const formatNumber = (value: number): string => {
    if (value >= 1e12) {
        return `${(value / 1e12).toFixed(2)}T`
    } else if (value >= 1e9) {
        return `${(value / 1e9).toFixed(2)}B`
    } else if (value >= 1e6) {
        return `${(value / 1e6).toFixed(2)}M`
    } else if (value >= 1e3) {
        return `${(value / 1e3).toFixed(2)}K`
    }
    return value.toFixed(2)
}

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

// 计算总价值
const totalValue = computed(() => {
    let total = 0
    if (!props.assetView) return 0
    
    Object.values(props.assetView).forEach(container => {
        Object.values(container.assets || {}).forEach(asset => {
            total += asset.price * asset.quantity
        })
    })
    return total
})

// 容器统计
interface ContainerStat {
    name: string
    totalQuantity: number
    totalValue: number
    percentage: number
    assets: AssetItem[]
}

const containerStats = computed<ContainerStat[]>(() => {
    if (!props.assetView) return []
    
    const statsMap = new Map<string, ContainerStat>()
    
    Object.values(props.assetView).forEach(container => {
        const containerName = container.name || '未知容器'
        let stat = statsMap.get(containerName)
        
        if (!stat) {
            stat = {
                name: containerName,
                totalQuantity: 0,
                totalValue: 0,
                percentage: 0,
                assets: []
            }
            statsMap.set(containerName, stat)
        }
        
        Object.values(container.assets || {}).forEach(asset => {
            const value = asset.price * asset.quantity
            stat.totalQuantity += asset.quantity
            stat.totalValue += value
            stat.assets.push({ ...asset })
        })
    })
    
    const stats = Array.from(statsMap.values())
    const total = totalValue.value
    
    stats.forEach(stat => {
        stat.percentage = total > 0 ? (stat.totalValue / total) * 100 : 0
    })
    
    // 按总价值降序排列
    return stats.sort((a, b) => b.totalValue - a.totalValue)
})

// 类型统计
interface TypeStat {
    classType: string
    totalQuantity: number
    totalValue: number
    percentage: number
    assets: AssetItem[]
}

const typeStats = computed<TypeStat[]>(() => {
    if (!props.assetView) return []
    
    const statsMap = new Map<string, TypeStat>()
    
    Object.values(props.assetView).forEach(container => {
        Object.values(container.assets || {}).forEach(asset => {
            const classType = asset.class_type || '未知类型'
            let stat = statsMap.get(classType)
            
            if (!stat) {
                stat = {
                    classType: classType,
                    totalQuantity: 0,
                    totalValue: 0,
                    percentage: 0,
                    assets: []
                }
                statsMap.set(classType, stat)
            }
            
            const value = asset.price * asset.quantity
            stat.totalQuantity += asset.quantity
            stat.totalValue += value
            
            // 检查是否已存在该资产，如果存在则累加数量
            const existingAsset = stat.assets.find(a => a.type_id === asset.type_id)
            if (existingAsset) {
                existingAsset.quantity += asset.quantity
            } else {
                stat.assets.push({ ...asset })
            }
        })
    })
    
    const stats = Array.from(statsMap.values())
    const total = totalValue.value
    
    stats.forEach(stat => {
        stat.percentage = total > 0 ? (stat.totalValue / total) * 100 : 0
        // 对资产按价值降序排列
        stat.assets.sort((a, b) => (b.price * b.quantity) - (a.price * a.quantity))
    })
    
    // 按总价值降序排列
    return stats.sort((a, b) => b.totalValue - a.totalValue)
})

// 详情弹窗
const containerDetailDialogVisible = ref(false)
const typeDetailDialogVisible = ref(false)

// 展开/折叠状态
const expandedContainers = ref<Set<string>>(new Set())
const expandedTypes = ref<Set<string>>(new Set())

const toggleContainer = (name: string) => {
    if (expandedContainers.value.has(name)) {
        expandedContainers.value.delete(name)
    } else {
        expandedContainers.value.add(name)
    }
}

const toggleType = (classType: string) => {
    if (expandedTypes.value.has(classType)) {
        expandedTypes.value.delete(classType)
    } else {
        expandedTypes.value.add(classType)
    }
}

// 计算资产在容器中的占比
const getAssetPercentageInContainer = (asset: AssetItem, containerStat: ContainerStat): number => {
    if (containerStat.totalValue === 0) return 0
    const assetValue = asset.price * asset.quantity
    return (assetValue / containerStat.totalValue) * 100
}

// 计算资产在类型中的占比
const getAssetPercentageInType = (asset: AssetItem, typeStat: TypeStat): number => {
    if (typeStat.totalValue === 0) return 0
    const assetValue = asset.price * asset.quantity
    return (assetValue / typeStat.totalValue) * 100
}

// ECharts 图表
const containerChartRef = ref<HTMLElement>()
const typeChartRef = ref<HTMLElement>()
let containerChartInstance: echarts.ECharts | null = null
let typeChartInstance: echarts.ECharts | null = null

// 初始化容器分类饼图
const initContainerChart = () => {
    if (!containerChartRef.value) return
    
    const data = containerStats.value
    if (!data || data.length === 0) {
        if (containerChartInstance) {
            containerChartInstance.dispose()
            containerChartInstance = null
        }
        return
    }
    
    if (!containerChartInstance) {
        containerChartInstance = echarts.init(containerChartRef.value)
    }
    
    const chartData = data.map(item => ({
        name: item.name,
        value: item.totalValue
    }))
    
    const total = totalValue.value
    
    const option: EChartsOption = {
        title: {
            text: '容器分类占比',
            left: 'center',
            textStyle: {
                fontSize: 16
            }
        },
        tooltip: {
            trigger: 'item',
            formatter: (params: any) => {
                const percentage = ((params.value / total) * 100).toFixed(2)
                return `${params.name}<br/>价值: ${formatNumber(params.value)} ISK<br/>占比: ${percentage}%`
            }
        },
        legend: {
            orient: 'vertical',
            left: 'left',
            top: 'middle'
        },
        series: [
            {
                name: '容器价值',
                type: 'pie',
                radius: ['40%', '70%'],
                avoidLabelOverlap: false,
                itemStyle: {
                    borderRadius: 10,
                    borderColor: '#fff',
                    borderWidth: 2
                },
                label: {
                    show: true,
                    formatter: (params: any) => {
                        const percentage = ((params.value / total) * 100).toFixed(1)
                        return `${params.name}\n${percentage}%`
                    }
                },
                emphasis: {
                    label: {
                        show: true,
                        fontSize: 16,
                        fontWeight: 'bold'
                    }
                },
                data: chartData
            }
        ]
    }
    
    containerChartInstance.setOption(option, true)
    containerChartInstance.resize()
}

// 初始化类型分类饼图
const initTypeChart = () => {
    if (!typeChartRef.value) return
    
    const data = typeStats.value
    if (!data || data.length === 0) {
        if (typeChartInstance) {
            typeChartInstance.dispose()
            typeChartInstance = null
        }
        return
    }
    
    if (!typeChartInstance) {
        typeChartInstance = echarts.init(typeChartRef.value)
    }
    
    const chartData = data.map(item => ({
        name: item.classType,
        value: item.totalValue
    }))
    
    const total = totalValue.value
    
    const option: EChartsOption = {
        title: {
            text: '类型分类占比',
            left: 'center',
            textStyle: {
                fontSize: 16
            }
        },
        tooltip: {
            trigger: 'item',
            formatter: (params: any) => {
                const percentage = ((params.value / total) * 100).toFixed(2)
                return `${params.name}<br/>价值: ${formatNumber(params.value)} ISK<br/>占比: ${percentage}%`
            }
        },
        legend: {
            orient: 'vertical',
            left: 'left',
            top: 'middle'
        },
        series: [
            {
                name: '类型价值',
                type: 'pie',
                radius: ['40%', '70%'],
                avoidLabelOverlap: false,
                itemStyle: {
                    borderRadius: 10,
                    borderColor: '#fff',
                    borderWidth: 2
                },
                label: {
                    show: true,
                    formatter: (params: any) => {
                        const percentage = ((params.value / total) * 100).toFixed(1)
                        return `${params.name}\n${percentage}%`
                    }
                },
                emphasis: {
                    label: {
                        show: true,
                        fontSize: 16,
                        fontWeight: 'bold'
                    }
                },
                data: chartData
            }
        ]
    }
    
    typeChartInstance.setOption(option, true)
    typeChartInstance.resize()
}

// 更新图表
const updateCharts = async () => {
    await nextTick()
    if (containerChartRef.value && typeChartRef.value) {
        const containerContainer = containerChartRef.value
        const typeContainer = typeChartRef.value
        
        if (containerContainer.offsetWidth > 0 && typeContainer.offsetWidth > 0) {
            initContainerChart()
            initTypeChart()
        } else {
            setTimeout(() => {
                if (containerContainer.offsetWidth > 0 && typeContainer.offsetWidth > 0) {
                    initContainerChart()
                    initTypeChart()
                } else {
                    setTimeout(() => {
                        initContainerChart()
                        initTypeChart()
                    }, 200)
                }
            }, 100)
        }
    }
}

// 监听数据变化
watch(() => props.assetView, () => {
    if (props.assetView && Object.keys(props.assetView).length > 0) {
        updateCharts()
    }
}, { deep: true, immediate: false })

watch(containerStats, () => {
    if (containerStats.value && containerStats.value.length > 0) {
        updateCharts()
    }
}, { deep: true, immediate: false })

watch(typeStats, () => {
    if (typeStats.value && typeStats.value.length > 0) {
        updateCharts()
    }
}, { deep: true, immediate: false })

// 监听容器尺寸变化
const observeContainer = () => {
    if (containerChartRef.value && typeChartRef.value) {
        const observer = new ResizeObserver(() => {
            if (containerChartInstance) {
                containerChartInstance.resize()
            }
            if (typeChartInstance) {
                typeChartInstance.resize()
            }
        })
        
        observer.observe(containerChartRef.value)
        observer.observe(typeChartRef.value)
        
        return observer
    }
    return null
}

// 窗口大小调整处理函数
const handleResize = () => {
    containerChartInstance?.resize()
    typeChartInstance?.resize()
}

// ResizeObserver 实例
let containerObserver: ResizeObserver | null = null

// 组件挂载
onMounted(async () => {
    await nextTick()
    await nextTick()
    
    setTimeout(() => {
        containerObserver = observeContainer()
    }, 100)
    
    setTimeout(() => {
        updateCharts()
    }, 300)
    
    window.addEventListener('resize', handleResize)
})

// 组件卸载
onUnmounted(() => {
    if (containerObserver) {
        containerObserver.disconnect()
        containerObserver = null
    }
    
    if (containerChartInstance) {
        containerChartInstance.dispose()
        containerChartInstance = null
    }
    if (typeChartInstance) {
        typeChartInstance.dispose()
        typeChartInstance = null
    }
    
    window.removeEventListener('resize', handleResize)
})

</script>

<template>
    <div v-loading="loading" class="statistics-view-content">
        <div v-if="!loading && (!assetView || Object.keys(assetView).length === 0)" class="empty-state">
            <el-empty description="暂无数据" />
        </div>
        <div v-else class="statistics-view-container">
            <!-- 工具栏 -->
            <div class="toolbar">
                <div class="toolbar-left">
                    <el-button 
                        type="primary" 
                        @click="containerDetailDialogVisible = true"
                        class="toolbar-button"
                    >
                        容器详情
                    </el-button>
                    <el-button 
                        type="primary" 
                        @click="typeDetailDialogVisible = true"
                        class="toolbar-button"
                    >
                        分类详情
                    </el-button>
                </div>
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

            <!-- 总价值卡片 -->
            <el-card class="total-value-card" shadow="hover">
                <div class="total-value-content">
                    <div class="total-value-label">资产总价值</div>
                    <el-statistic 
                        :value="totalValue" 
                        :precision="2" 
                        suffix=" ISK"
                        class="total-value-statistic"
                    />
                </div>
            </el-card>

            <!-- 饼图展示区 -->
            <div class="charts-container">
                <el-card class="chart-card" shadow="hover">
                    <div ref="containerChartRef" class="chart-container"></div>
                </el-card>
                <el-card class="chart-card" shadow="hover">
                    <div ref="typeChartRef" class="chart-container"></div>
                </el-card>
            </div>
        </div>
    </div>

    <!-- 容器详情弹窗 -->
    <el-dialog 
        v-model="containerDetailDialogVisible" 
        title="容器详情" 
        width="80%" 
        class="detail-dialog"
    >
        <div class="detail-content">
            <el-card 
                v-for="stat in containerStats" 
                :key="stat.name"
                class="outer-card"
                shadow="hover"
            >
                <template #header>
                    <div class="card-header">
                        <div class="header-info">
                            <span class="header-title">{{ stat.name }}</span>
                            <div class="header-stats">
                                <el-tag type="info" size="large">数量: {{ formatNumber(stat.totalQuantity) }}</el-tag>
                                <el-tag type="success" size="large">价值: {{ formatNumber(stat.totalValue) }} ISK</el-tag>
                                <el-tag type="warning" size="large">占比: {{ stat.percentage.toFixed(2) }}%</el-tag>
                            </div>
                        </div>
                        <el-button 
                            :icon="expandedContainers.has(stat.name) ? ArrowUp : ArrowDown"
                            circle
                            @click="toggleContainer(stat.name)"
                            class="expand-button"
                        />
                    </div>
                </template>
                <div v-if="expandedContainers.has(stat.name)" class="inner-cards">
                    <el-card 
                        v-for="asset in stat.assets" 
                        :key="asset.type_id"
                        class="inner-card"
                        shadow="never"
                    >
                        <div class="asset-card-content">
                            <el-avatar 
                                :size="48" 
                                :src="`https://imageserver.eveonline.com/Type/${asset.type_id}_64.png`" 
                                shape="square"
                                class="asset-avatar"
                            />
                            <div class="asset-info">
                                <div class="asset-name-zh">{{ asset.type_name_zh || asset.type_name }}</div>
                                <div class="asset-name-en">{{ asset.type_name }}</div>
                            </div>
                            <div class="asset-stats">
                                <div class="stat-item">
                                    <span class="stat-label">数量:</span>
                                    <span class="stat-value">{{ formatNumber(asset.quantity) }}</span>
                                </div>
                                <div class="stat-item">
                                    <span class="stat-label">价值:</span>
                                    <span class="stat-value">{{ formatNumber(asset.price * asset.quantity) }} ISK</span>
                                </div>
                                <div class="stat-item">
                                    <span class="stat-label">占比:</span>
                                    <span class="stat-value">{{ getAssetPercentageInContainer(asset, stat).toFixed(2) }}%</span>
                                </div>
                            </div>
                        </div>
                    </el-card>
                </div>
            </el-card>
        </div>
    </el-dialog>

    <!-- 分类详情弹窗 -->
    <el-dialog 
        v-model="typeDetailDialogVisible" 
        title="分类详情" 
        width="80%" 
        class="detail-dialog"
    >
        <div class="detail-content">
            <el-card 
                v-for="stat in typeStats" 
                :key="stat.classType"
                class="outer-card"
                shadow="hover"
            >
                <template #header>
                    <div class="card-header">
                        <div class="header-info">
                            <span class="header-title">{{ stat.classType }}</span>
                            <div class="header-stats">
                                <el-tag type="info" size="large">数量: {{ formatNumber(stat.totalQuantity) }}</el-tag>
                                <el-tag type="success" size="large">价值: {{ formatNumber(stat.totalValue) }} ISK</el-tag>
                                <el-tag type="warning" size="large">占比: {{ stat.percentage.toFixed(2) }}%</el-tag>
                            </div>
                        </div>
                        <el-button 
                            :icon="expandedTypes.has(stat.classType) ? ArrowUp : ArrowDown"
                            circle
                            @click="toggleType(stat.classType)"
                            class="expand-button"
                        />
                    </div>
                </template>
                <div v-if="expandedTypes.has(stat.classType)" class="inner-cards">
                    <el-card 
                        v-for="asset in stat.assets" 
                        :key="asset.type_id"
                        class="inner-card"
                        shadow="never"
                    >
                        <div class="asset-card-content">
                            <el-avatar 
                                :size="48" 
                                :src="`https://imageserver.eveonline.com/Type/${asset.type_id}_64.png`" 
                                shape="square"
                                class="asset-avatar"
                            />
                            <div class="asset-info">
                                <div class="asset-name-zh">{{ asset.type_name_zh || asset.type_name }}</div>
                                <div class="asset-name-en">{{ asset.type_name }}</div>
                            </div>
                            <div class="asset-stats">
                                <div class="stat-item">
                                    <span class="stat-label">数量:</span>
                                    <span class="stat-value">{{ formatNumber(asset.quantity) }}</span>
                                </div>
                                <div class="stat-item">
                                    <span class="stat-label">价值:</span>
                                    <span class="stat-value">{{ formatNumber(asset.price * asset.quantity) }} ISK</span>
                                </div>
                                <div class="stat-item">
                                    <span class="stat-label">占比:</span>
                                    <span class="stat-value">{{ getAssetPercentageInType(asset, stat).toFixed(2) }}%</span>
                                </div>
                            </div>
                        </div>
                    </el-card>
                </div>
            </el-card>
        </div>
    </el-dialog>
</template>

<style scoped>
.statistics-view-content {
    min-height: 400px;
}

.empty-state {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 400px;
}

.statistics-view-container {
    display: flex;
    flex-direction: column;
    gap: 20px;
}

/* 工具栏 */
.toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding: 16px;
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    border-radius: 8px;
}

.toolbar-left {
    display: flex;
    gap: 12px;
    flex: 1;
}

.toolbar-right {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-shrink: 0;
}

.toolbar-button {
    font-size: 14px;
    padding: 10px 20px;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
    transition: all 0.3s ease;
}

.toolbar-button:hover {
    box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
    transform: translateY(-1px);
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

/* 总价值卡片 */
.total-value-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
    color: white;
}

.total-value-card :deep(.el-card__body) {
    padding: 24px;
}

.total-value-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
}

.total-value-label {
    font-size: 18px;
    font-weight: 600;
    opacity: 0.9;
}

.total-value-statistic {
    margin-top: 8px;
}

.total-value-statistic :deep(.el-statistic__number) {
    font-size: 36px;
    font-weight: 700;
    color: white;
}

.total-value-statistic :deep(.el-statistic__suffix) {
    font-size: 20px;
    color: rgba(255, 255, 255, 0.9);
    margin-left: 8px;
}

/* 饼图容器 */
.charts-container {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 20px;
}

.chart-card {
    border-radius: 8px;
}

.chart-card :deep(.el-card__body) {
    padding: 16px;
}

.chart-container {
    width: 100%;
    height: 400px;
}

/* 详情弹窗 */
.detail-dialog :deep(.el-dialog__body) {
    padding: 24px;
    max-height: 70vh;
    overflow-y: auto;
}

.detail-content {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

/* 外层卡片 */
.outer-card {
    border-radius: 8px;
    transition: all 0.3s ease;
}

.outer-card:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.header-info {
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex: 1;
}

.header-title {
    font-size: 18px;
    font-weight: 600;
    color: #303133;
}

.header-stats {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.expand-button {
    flex-shrink: 0;
}

/* 内层卡片 */
.inner-cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 12px;
    margin-top: 16px;
}

.inner-card {
    border-radius: 6px;
    border: 1px solid #e4e7ed;
}

.inner-card :deep(.el-card__body) {
    padding: 12px;
}

.asset-card-content {
    display: flex;
    align-items: center;
    gap: 12px;
}

.asset-avatar {
    flex-shrink: 0;
    border: 2px solid #f0f0f0;
    border-radius: 4px;
}

.asset-info {
    flex: 1;
    min-width: 0;
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
    word-break: break-word;
}

.asset-stats {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex-shrink: 0;
    text-align: right;
}

.stat-item {
    display: flex;
    align-items: center;
    gap: 8px;
}

.stat-label {
    font-size: 12px;
    color: #909399;
}

.stat-value {
    font-size: 13px;
    font-weight: 600;
    color: #303133;
}

/* 响应式设计 */
@media (max-width: 1200px) {
    .charts-container {
        grid-template-columns: 1fr;
    }
}

@media (max-width: 768px) {
    .toolbar {
        flex-direction: column;
        align-items: stretch;
    }
    
    .toolbar-left {
        width: 100%;
        justify-content: center;
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
    
    .inner-cards {
        grid-template-columns: 1fr;
    }
    
    .header-stats {
        flex-direction: column;
    }
    
    .asset-card-content {
        flex-direction: column;
        align-items: flex-start;
    }
    
    .asset-stats {
        width: 100%;
        text-align: left;
    }
}
</style>

