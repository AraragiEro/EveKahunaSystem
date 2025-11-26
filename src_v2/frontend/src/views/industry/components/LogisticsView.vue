<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'

// Props定义
const props = defineProps<{
    logisticsData: any[]
    selectedPlan: string | null
}>()

// 会计格式格式化函数
const formatAccounting = (value: number | string | null | undefined): string => {
    if (value === null || value === undefined || value === '') {
        return ''
    }
    const num = typeof value === 'string' ? parseFloat(value) : value
    if (isNaN(num)) {
        return String(value)
    }
    return num.toLocaleString('zh-CN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    })
}

// 复制单元格内容
const copyCellContent = async (content: string | number | null | undefined, fieldName: string = '') => {
    try {
        if (content === null || content === undefined || content === '') {
            ElMessage.warning('没有可复制的内容')
            return
        }
        const text = String(content)
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text)
            ElMessage.success(`已复制${fieldName ? ` ${fieldName} ` : ' '}到剪贴板`)
        } else {
            const textarea = document.createElement('textarea')
            textarea.value = text
            textarea.style.position = 'fixed'
            textarea.style.left = '-9999px'
            textarea.style.top = '-9999px'
            document.body.appendChild(textarea)
            textarea.select()
            textarea.setSelectionRange(0, text.length)
            try {
                const successful = document.execCommand('copy')
                if (successful) {
                    ElMessage.success(`已复制${fieldName ? ` ${fieldName} ` : ' '}到剪贴板`)
                } else {
                    throw new Error('execCommand 复制失败')
                }
            } finally {
                document.body.removeChild(textarea)
            }
        }
    } catch (error) {
        console.error('复制失败:', error)
        ElMessage.error('复制失败，请重试')
    }
}

// 表格数据
const tableData = computed(() => {
    if (!props.logisticsData || !Array.isArray(props.logisticsData)) {
        return []
    }
    return props.logisticsData.map(item => ({
        lack_type_name: item.lack_type_name || '',
        provide_quantity: item.provide_quantity || 0,
        provide_volume: item.provide_volume || 0,
        provide_system_name: item.provide_system_name || '',
        lack_system_name: item.lack_system_name || '',
        provide_system_distance: item.provide_system_distance || 0,
        provide_structure_name: item.provide_structure_name || '',
        lack_structure_name: item.lack_structure_name || ''
    }))
})

// 计算总体积总和
const totalVolume = computed(() => {
    if (!tableData.value || tableData.value.length === 0) {
        return 0
    }
    return tableData.value.reduce((sum, item) => {
        const volume = item.provide_volume || 0
        return sum + (typeof volume === 'number' ? volume : parseFloat(volume) || 0)
    }, 0)
})

// 图表相关
const graphContainerRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null

// 将3D坐标投影到2D平面（使用X-Y投影）
const project3DTo2D = (coord: number[]): [number, number] => {
    if (!coord || coord.length < 3) {
        return [0, 0]
    }
    // 使用X-Y投影，忽略Z轴
    return [coord[0], coord[1]]
}

// 归一化坐标函数，保留相对位置和距离关系
const normalizeCoordinates = (
    coordinates: Array<{ x: number; y: number }>,
    targetRange: { min: number; max: number } = { min: 0, max: 1000 }
): Array<{ x: number; y: number }> => {
    if (coordinates.length === 0) {
        return coordinates
    }

    // 找到所有坐标的最小值和最大值
    const xs = coordinates.map(c => c.x)
    const ys = coordinates.map(c => c.y)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)

    // 计算范围，使用较大的范围来保持宽高比
    const rangeX = maxX - minX || 1 // 避免除零
    const rangeY = maxY - minY || 1
    const maxRange = Math.max(rangeX, rangeY) // 使用最大范围保持比例
    const targetRangeSize = targetRange.max - targetRange.min

    // 归一化到目标范围，使用相同的缩放因子保持相对距离关系
    return coordinates.map(coord => {
        // 将坐标归一化到 [0, 1] 范围，使用相同的范围保持比例
        const normalizedX = (coord.x - minX) / maxRange
        const normalizedY = (coord.y - minY) / maxRange

        // 缩放到目标范围
        const scaledX = normalizedX * targetRangeSize + targetRange.min
        const scaledY = normalizedY * targetRangeSize + targetRange.min

        return { x: scaledX, y: scaledY }
    })
}

// 计算图表数据
const graphData = computed(() => {
    if (!props.logisticsData || !Array.isArray(props.logisticsData) || props.logisticsData.length === 0) {
        return { nodes: [], links: [] }
    }

    // 收集所有唯一的系统节点
    const systemMap = new Map<string, {
        id: string
        name: string
        system_id: number
        coordinate: number[]
        x: number
        y: number
    }>()

    // 收集所有边，聚合相同方向的边体积
    const edgeVolumeMap = new Map<string, number>()

    props.logisticsData.forEach(item => {
        const provideSystemId = String(item.provide_system_id)
        const lackSystemId = String(item.lack_system_id)
        const provideSystemName = item.provide_system_name || provideSystemId
        const lackSystemName = item.lack_system_name || lackSystemId

        // 添加出发地节点
        if (!systemMap.has(provideSystemId)) {
            const [x, y] = project3DTo2D(item.provide_system_coordinate || [0, 0, 0])
            systemMap.set(provideSystemId, {
                id: provideSystemId,
                name: provideSystemName,
                system_id: item.provide_system_id,
                coordinate: item.provide_system_coordinate || [0, 0, 0],
                x,
                y
            })
        }

        // 添加目的地节点
        if (!systemMap.has(lackSystemId)) {
            const [x, y] = project3DTo2D(item.lack_system_coordinate || [0, 0, 0])
            systemMap.set(lackSystemId, {
                id: lackSystemId,
                name: lackSystemName,
                system_id: item.lack_system_id,
                coordinate: item.lack_system_coordinate || [0, 0, 0],
                x,
                y
            })
        }

        // 聚合相同方向的边体积
        const edgeKey = `${provideSystemId}-${lackSystemId}`
        const currentVolume = item.provide_volume || 0
        edgeVolumeMap.set(edgeKey, (edgeVolumeMap.get(edgeKey) || 0) + currentVolume)
    })

    // 归一化所有节点的坐标
    const systemNodes = Array.from(systemMap.values())
    const normalizedCoords = normalizeCoordinates(
        systemNodes.map(node => ({ x: node.x, y: node.y })),
        { min: 0, max: 1000 }
    )

    // 更新节点坐标
    systemNodes.forEach((node, index) => {
        node.x = normalizedCoords[index].x
        node.y = normalizedCoords[index].y
    })

    // 检测往返边并分配curveness
    const edgeMap = new Map<string, {
        source: string
        target: string
        volume: number
        curveness: number
    }>()

    // 先收集所有边的键
    const allEdgeKeys = Array.from(edgeVolumeMap.keys())
    
    allEdgeKeys.forEach(edgeKey => {
        const [source, target] = edgeKey.split('-')
        const reverseKey = `${target}-${source}`
        const volume = edgeVolumeMap.get(edgeKey) || 0
        
        // 检查是否存在反向边
        const hasReverse = edgeVolumeMap.has(reverseKey)

        if (hasReverse) {
            // 如果存在反向边，检查当前边是否已经处理过
            if (edgeMap.has(reverseKey)) {
                // 反向边已存在，当前边使用负curveness
                edgeMap.set(edgeKey, {
                    source,
                    target,
                    volume,
                    curveness: 0.1
                })
            } else {
                // 反向边未处理，当前边使用正curveness
                edgeMap.set(edgeKey, {
                    source,
                    target,
                    volume,
                    curveness: 0.1
                })
            }
        } else {
            // 不存在反向边，使用直线
            edgeMap.set(edgeKey, {
                source,
                target,
                volume,
                curveness: 0.1
            })
        }
    })

    // 计算体积范围，用于设置线宽
    const volumes = Array.from(edgeMap.values()).map(e => e.volume).filter(v => v > 0)
    const minVolume = volumes.length > 0 ? Math.min(...volumes) : 1
    const maxVolume = volumes.length > 0 ? Math.max(...volumes) : 1

    // 构建节点数组
    const nodes = Array.from(systemMap.values()).map(system => ({
        id: system.id,
        name: system.name,
        x: system.x,
        y: system.y,
        symbolSize: 30,
        category: 0
    }))

    // 构建边数组
    const links = Array.from(edgeMap.values()).map(edge => {
        // 根据体积计算线宽（1-10之间）
        const lineWidth = volumes.length > 0 && maxVolume > minVolume
            ? 5 + (edge.volume - minVolume) / (maxVolume - minVolume) * 9
            : 10

        // 根据线宽计算箭头大小（箭头大小应该与线宽成比例，确保箭头足够明显）
        const arrowSize = Math.max(10, lineWidth * 4)

        return {
            source: edge.source,
            target: edge.target,
            value: edge.volume,
            symbol: ['None', 'arrow'], // 起点无符号，终点显示箭头
            symbolSize: [0, arrowSize], // 箭头大小
            lineStyle: {
                width: lineWidth,
                curveness: edge.curveness,
                color: '#F95EFF'
            },
            label: {
                show: true,
                fontSize: 15,
                formatter: `${formatAccounting(edge.volume)} m³`
            }
        }
    })

    return { nodes, links }
})

// 初始化图表
const initChart = () => {
    if (!graphContainerRef.value) return

    const data = graphData.value
    if (!data || data.nodes.length === 0) {
        if (chartInstance) {
            chartInstance.dispose()
            chartInstance = null
        }
        return
    }

    if (!chartInstance) {
        chartInstance = echarts.init(graphContainerRef.value)
    }

    // 计算节点坐标范围，用于设置合适的视图
    const xs = data.nodes.map(n => n.x)
    const ys = data.nodes.map(n => n.y)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const rangeX = maxX - minX || 1
    const rangeY = maxY - minY || 1

    const option: EChartsOption = {
        title: {
            text: '物流关系图',
            left: 'center',
            top: 10
        },
        tooltip: {
            trigger: 'item',
            formatter: (params: any) => {
                if (params.dataType === 'node') {
                    return `${params.data.name}<br/>系统ID: ${params.data.id}`
                } else if (params.dataType === 'edge') {
                    return `${params.data.source} → ${params.data.target}<br/>运输量: ${formatAccounting(params.data.value)} m³`
                }
                return ''
            }
        },
        series: [{
            type: 'graph',
            layout: 'none',
            data: data.nodes,
            links: data.links,
            roam: true,
            zoom: 1,
            label: {
                show: true,
                position: 'right',
                formatter: '{b}'
            },
            edgeLabel: {
                show: true,
                formatter: '{c}'
            },
            lineStyle: {
                color: '#5470c6',
                width: 2,
                curveness: 0
            },
            emphasis: {
                focus: 'adjacency',
                lineStyle: {
                    width: 4
                }
            },
            categories: [{
                name: 'system'
            }]
        }]
    }

    chartInstance.setOption(option, true) // 使用 notMerge=true 确保完全更新
    // 确保图表正确渲染
    chartInstance.resize()
}

// 更新图表
const updateChart = async () => {
    await nextTick()
    if (graphContainerRef.value) {
        const container = graphContainerRef.value
        
        if (container.offsetWidth > 0 && container.offsetHeight > 0) {
            initChart()
        } else {
            setTimeout(() => {
                if (container.offsetWidth > 0 && container.offsetHeight > 0) {
                    initChart()
                } else {
                    setTimeout(() => {
                        initChart()
                    }, 200)
                }
            }, 100)
        }
    }
}

// 监听容器尺寸变化，确保图表能正确初始化
const observeContainer = () => {
    if (graphContainerRef.value) {
        const observer = new ResizeObserver(() => {
            // 当容器尺寸变化时，如果图表已初始化，重新调整大小
            if (chartInstance) {
                chartInstance.resize()
            }
        })
        
        observer.observe(graphContainerRef.value)
        
        return observer
    }
    return null
}

// 窗口大小调整处理函数
const handleResize = () => {
    if (chartInstance) {
        chartInstance.resize()
    }
}

// ResizeObserver 实例
let containerObserver: ResizeObserver | null = null

// 监听数据变化
watch(() => props.logisticsData, () => {
    updateChart()
}, { deep: true, immediate: false })

watch(graphData, () => {
    if (graphData.value && graphData.value.nodes.length > 0) {
        updateChart()
    }
}, { deep: true, immediate: false })

// 组件挂载
onMounted(async () => {
    // 等待多个 nextTick 确保 DOM 完全渲染
    await nextTick()
    await nextTick()
    
    // 设置 ResizeObserver 监听容器尺寸变化
    setTimeout(() => {
        containerObserver = observeContainer()
    }, 100)
    
    // 延迟初始化图表，确保容器有尺寸
    setTimeout(() => {
        updateChart()
    }, 300)
    
    // 响应式调整图表大小
    window.addEventListener('resize', handleResize)
})

// 组件卸载
onUnmounted(() => {
    // 清理 ResizeObserver
    if (containerObserver) {
        containerObserver.disconnect()
        containerObserver = null
    }
    
    // 清理图表实例
    if (chartInstance) {
        chartInstance.dispose()
        chartInstance = null
    }
    // 移除事件监听
    window.removeEventListener('resize', handleResize)
})

</script>

<template>
    <div class="logistics-view">
        <el-card shadow="never">
            <template #header>
                <div class="card-header">
                    <span>物流视图</span>
                    <span v-if="selectedPlan" class="plan-name">{{ selectedPlan }}</span>
                </div>
            </template>
            <div class="content-container">
                <el-row :gutter="20">
                    <!-- 图表区域 - 独占一行 -->
                    <el-col :span="24">
                        <el-card shadow="never" class="chart-card">
                            <template #header>
                                <span>星系图</span>
                            </template>
                            <div ref="graphContainerRef" class="chart-container"></div>
                        </el-card>
                    </el-col>
                    <!-- 表格区域 - 独占一行 -->
                    <el-col :span="24">
                        <el-card shadow="never" class="table-card">
                            <template #header>
                                <span>运力表</span>
                            </template>
                            <el-table
                                :data="tableData"
                                :key="`logistics-table-${selectedPlan || 'default'}`"
                                border
                                max-height="600px"
                                show-overflow-tooltip
                            >
                                <el-table-column label="物品名称" prop="lack_type_name" width="150">
                                    <template #default="{ row }">
                                        <div 
                                            class="copyable-cell" 
                                            @click="copyCellContent(row.lack_type_name, '物品名称')"
                                            :title="`点击复制: ${row.lack_type_name || ''}`"
                                        >
                                            {{ row.lack_type_name }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="总数量" prop="provide_quantity" width="150">
                                    <template #default="{ row }">
                                        <div 
                                            class="copyable-cell" 
                                            @click="copyCellContent(row.provide_quantity, '总数量')"
                                            :title="`点击复制: ${row.provide_quantity || ''}`"
                                        >
                                            {{ formatAccounting(row.provide_quantity) }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="总体积 (m³)" prop="provide_volume" width="150">
                                    <template #header>
                                        <span>总体积 (m³)</span>
                                        <div style="font-size: 12px; color: #909399; font-weight: normal; margin-top: 4px;">
                                            总计: {{ formatAccounting(totalVolume) }}
                                        </div>
                                    </template>
                                    <template #default="{ row }">
                                        <div 
                                            class="copyable-cell" 
                                            @click="copyCellContent(row.provide_volume, '总体积')"
                                            :title="`点击复制: ${row.provide_volume || ''}`"
                                        >
                                            {{ formatAccounting(row.provide_volume) }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="出发地" prop="provide_structure_name" width="250">
                                    <template #default="{ row }">
                                        <div 
                                            class="copyable-cell" 
                                            @click="copyCellContent(row.provide_structure_name, '出发地')"
                                            :title="`点击复制: ${row.provide_structure_name || ''}`"
                                        >
                                            {{ row.provide_structure_name }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="目的地" prop="lack_structure_name" width="250">
                                    <template #default="{ row }">
                                        <div 
                                            class="copyable-cell" 
                                            @click="copyCellContent(row.lack_structure_name, '目的地')"
                                            :title="`点击复制: ${row.lack_structure_name || ''}`"
                                        >
                                            {{ row.lack_structure_name }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="距离(Ly)" prop="provide_system_distance" width="100">
                                    <template #default="{ row }">
                                        <div 
                                            class="copyable-cell" 
                                            @click="copyCellContent(row.provide_system_distance, '距离')"
                                            :title="`点击复制: ${row.provide_system_distance || ''}`"
                                        >
                                            {{ formatAccounting(row.provide_system_distance) }}
                                        </div>
                                    </template>
                                </el-table-column>
                            </el-table>
                        </el-card>
                    </el-col>
                </el-row>
            </div>
        </el-card>
    </div>
</template>

<style scoped>
.logistics-view {
    width: 100%;
}

.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.plan-name {
    font-size: 12px;
    color: #909399;
}

.content-container {
    padding: 0;
}

.chart-card {
    margin-bottom: 20px;
}

.table-card {
    height: 100%;
}

.chart-container {
    width: 100%;
    max-height: 80vh;
    min-height: 400px;
    height: 80vh;
}

.copyable-cell {
    cursor: pointer;
    user-select: none;
}

.copyable-cell:hover {
    color: #409eff;
    text-decoration: underline;
}
</style>

