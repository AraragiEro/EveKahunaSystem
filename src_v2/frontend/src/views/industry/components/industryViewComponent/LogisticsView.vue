<script setup lang="ts">
/* eslint-disable @typescript-eslint/no-explicit-any -- 物流数据沿用后端原始结构（历史 any 契约），P2 只做 KCard/KTable/KEmpty 收敛，未改数据契约 */
import KTable from '@/components/k/KTable.vue'
import KEmpty from '@/components/k/KEmpty.vue'
import KCard from '@/components/k/KCard.vue'
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { getChartThemeColors, themedTooltip, onThemeTokenChange } from '@/utils/echartsTheme'

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
        lack_type_id: item.lack_type_id || 0,
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


// 筛选状态
const selectedDeparture = ref<string>('')
const selectedDestination = ref<string>('')

// 出发地筛选选项
const departureFilterOptions = computed(() => {
    const uniqueValues = new Set<string>()
    tableData.value.forEach(item => {
        if (item.provide_structure_name) {
            uniqueValues.add(item.provide_structure_name)
        }
    })
    return Array.from(uniqueValues).sort()
})

// 目的地筛选选项
const destinationFilterOptions = computed(() => {
    const uniqueValues = new Set<string>()
    tableData.value.forEach(item => {
        if (item.lack_structure_name) {
            uniqueValues.add(item.lack_structure_name)
        }
    })
    return Array.from(uniqueValues).sort()
})

// 过滤后的表格数据
const filteredTableData = computed(() => {
    let result = tableData.value

    if (selectedDeparture.value) {
        result = result.filter(item => item.provide_structure_name === selectedDeparture.value)
    }

    if (selectedDestination.value) {
        result = result.filter(item => item.lack_structure_name === selectedDestination.value)
    }

    return result
})

// 清除筛选
const clearFilters = () => {
    selectedDeparture.value = ''
    selectedDestination.value = ''
}

// 图表相关
const graphContainerRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null
let cleanupThemeWatcher: (() => void) | null = null

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
    const c = getChartThemeColors()
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
    const volumes = Array.from(edgeMap.values()).map(e => e.volume).filter(v => v> 0)
    const minVolume = volumes.length> 0 ? Math.min(...volumes) : 1
    const maxVolume = volumes.length> 0 ? Math.max(...volumes) : 1

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
        const lineWidth = volumes.length> 0 && maxVolume> minVolume
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
                color: c.primary
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

// 没有可绘制的物流关系时给一句提示，避免图表区域一片空白
const hasGraphData = computed(() => (graphData.value?.nodes?.length ?? 0) > 0)

// 初始化图表
const initChart = () => {
    const c = getChartThemeColors()
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
    const option: EChartsOption = {
        // 标题交给卡片头部，图内不再重复画（否则会压在节点/连线标签上）
        tooltip: {
            ...themedTooltip(c),
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
                color: c.text,
                formatter: '{b}'
            },
            edgeLabel: {
                show: true,
                color: c.textSecondary,
                formatter: '{c}'
            },
            lineStyle: {
                color: c.primary,
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

        if (container.offsetWidth> 0 && container.offsetHeight> 0) {
            initChart()
        } else {
            setTimeout(() => {
                if (container.offsetWidth> 0 && container.offsetHeight> 0) {
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

// 窗口大小调整处理函数 (RAF throttle)
let resizeRAF: number | null = null
const handleResize = () => {
    if (resizeRAF !== null) return
    resizeRAF = requestAnimationFrame(() => {
        if (chartInstance) {
            chartInstance.resize()
        }
        resizeRAF = null
    })
}

// ResizeObserver 实例
let containerObserver: ResizeObserver | null = null

// 响应式布局相关
const isLargeScreen = ref(window.innerWidth>= 1920)
const splitPosition = ref(50) // 分割线位置，百分比
const isDragging = ref(false)
const splitContainerRef = ref<HTMLElement>()

// 监听窗口大小变化 (RAF throttle for layout)
let layoutResizeRAF: number | null = null
const handleWindowResize = () => {
    if (layoutResizeRAF !== null) return
    layoutResizeRAF = requestAnimationFrame(() => {
        isLargeScreen.value = window.innerWidth >= 1920
        if (chartInstance) {
            chartInstance.resize()
        }
        layoutResizeRAF = null
    })
}

// 拖拽分割线相关
let resizeTimer: number | null = null

const startDrag = (e: MouseEvent) => {
    if (!isLargeScreen.value) return
    isDragging.value = true
    document.addEventListener('mousemove', onDrag)
    document.addEventListener('mouseup', stopDrag)
    e.preventDefault()
}

const onDrag = (e: MouseEvent) => {
    if (!isDragging.value || !splitContainerRef.value) return

    const container = splitContainerRef.value
    const rect = container.getBoundingClientRect()
    const x = e.clientX - rect.left
    const percentage = (x / rect.width) * 100

    // 限制分割线位置在 20% 到 80% 之间
    const clampedPercentage = Math.max(20, Math.min(80, percentage))
    splitPosition.value = clampedPercentage

    // 使用防抖来优化图表调整性能
    if (resizeTimer) {
        cancelAnimationFrame(resizeTimer)
    }
    resizeTimer = requestAnimationFrame(() => {
        if (chartInstance) {
            chartInstance.resize()
        }
    })
}

const stopDrag = () => {
    isDragging.value = false
    document.removeEventListener('mousemove', onDrag)
    document.removeEventListener('mouseup', stopDrag)

    // 清理防抖定时器
    if (resizeTimer) {
        cancelAnimationFrame(resizeTimer)
        resizeTimer = null
    }

    // 拖拽结束后重新调整图表大小
    if (chartInstance) {
        setTimeout(() => {
            chartInstance?.resize()
        }, 100)
    }
}

// 监听数据变化
watch(() => props.logisticsData, () => {
    updateChart()
}, { deep: true, immediate: false })

watch(graphData, () => {
    if (graphData.value && graphData.value.nodes.length> 0) {
        updateChart()
    }
}, { deep: true, immediate: false })

// 监听响应式布局变化：跨过 1920 断点时图表容器会被 v-if 重建，
// 旧实例还绑在已销毁的 DOM 上（resize() 无效），必须销毁后重新初始化，否则图会变空白
watch(isLargeScreen, () => {
    if (chartInstance) {
        chartInstance.dispose()
        chartInstance = null
    }
    setTimeout(() => {
        initChart()
    }, 120)
})

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
    // 监听窗口大小变化以更新响应式布局
    window.addEventListener('resize', handleWindowResize)
    cleanupThemeWatcher = onThemeTokenChange(() => {
        updateChart()
    })
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
    if (resizeRAF !== null) cancelAnimationFrame(resizeRAF)
    if (layoutResizeRAF !== null) cancelAnimationFrame(layoutResizeRAF)
    window.removeEventListener('resize', handleResize)
    window.removeEventListener('resize', handleWindowResize)
    cleanupThemeWatcher?.()
    cleanupThemeWatcher = null
    // 清理拖拽事件
    stopDrag()
})

// footer 汇总：只合计体积列
const volumeSummary = ({ columns, data }: { columns: any[], data: any[] }) => {
    return columns.map((col: any, index: number) => {
        if (index === 0) return '合计'
        const prop = col.property
        if (prop !== 'provide_volume') return ''
        const total = (data || []).reduce((s: number, row: any) => s + (Number(row?.[prop]) || 0), 0)
        return formatAccounting(total)
    })
}
</script>

<template>
    <div class="logistics-view">
        <KCard>
            <template #header>
                <div class="card-header">
                    <span>物流视图</span>
                    <span v-if="selectedPlan" class="plan-name">{{ selectedPlan }}</span>
                </div>
            </template>
            <div class="content-container">
                <!-- 大屏幕：图表和表格在同一行，中间有可拖动分割线 -->
                <div v-if="isLargeScreen" ref="splitContainerRef" class="split-container">
                    <div class="split-pane chart-pane" :style="{ width: `${splitPosition}%` }">
                        <KCard class="chart-card">
                            <template #header>
                                <span>物流关系图</span>
                            </template>
                            <div class="chart-wrapper">
                                <div ref="graphContainerRef" class="chart-container"></div>
                                <div v-if="!hasGraphData" class="chart-empty">
                                    <KEmpty why="当前计划没有可绘制的物流关系" size="sm" />
                                </div>
                            </div>
                        </KCard>
                    </div>
                    <div class="split-divider" :class="{ dragging: isDragging }" @mousedown="startDrag">
                        <div class="split-handle"></div>
                    </div>
                    <div class="split-pane table-pane" :style="{ width: `${100 - splitPosition}%` }">
                        <KCard class="table-card">
                            <template #header>
                                <span>运力表</span>
                            </template>
                            <!-- 筛选器 -->
                            <div class="filter-container">
                                <el-select v-model="selectedDeparture" placeholder="请选择出发地" clearable
                                    style="width: 200px; margin-right: 10px;">
                                    <el-option v-for="item in departureFilterOptions" :key="item" :label="item"
                                        :value="item" />
                                </el-select>
                                <el-select v-model="selectedDestination" placeholder="请选择目的地" clearable
                                    style="width: 200px; margin-right: 10px;">
                                    <el-option v-for="item in destinationFilterOptions" :key="item" :label="item"
                                        :value="item" />
                                </el-select>
                                <el-button v-if="selectedDeparture || selectedDestination" type="primary" plain
                                    size="small" @click="clearFilters">
                                    清除筛选
                                </el-button>
                            </div>
                            <KTable class="k-report-table" :data="filteredTableData" show-summary :summary-method="volumeSummary" :key="`logistics-table-${selectedPlan || 'default'}`"
                                border max-height="80vh">
                                <el-table-column label="icon" width="70">
                                    <template #default="{ row }">
                                        <img :src="`https://imageserver.eveonline.com/types/${row.lack_type_id}/icon`"
                                            alt="icon" width="40" height="40" style="object-fit: contain" loading="lazy" />
                                    </template>
                                </el-table-column>
                                <el-table-column label="物品名称" prop="lack_type_name" width="150">
                                    <template #default="{ row }">
                                        <div class="copyable-cell" @click="copyCellContent(row.lack_type_name, '物品名称')"
                                            :title="`点击复制: ${row.lack_type_name || ''}`">
                                            {{ row.lack_type_name }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="总数量" prop="provide_quantity" width="150">
                                    <template #default="{ row }">
                                        <div class="copyable-cell" @click="copyCellContent(row.provide_quantity, '总数量')"
                                            :title="`点击复制: ${row.provide_quantity || ''}`">
                                            {{ formatAccounting(row.provide_quantity) }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="总体积 (m³)" prop="provide_volume" width="150" align="right" sortable="custom">
                                    <template #header>
                                        <span>总体积 (m³)</span>
                                        <div
                                            style="font-size: 12px; color: #909399; font-weight: normal; margin-top: 4px;">
            
                                        </div>
                                    </template>
                                    <template #default="{ row }">
                                        <div class="copyable-cell" @click="copyCellContent(row.provide_volume, '总体积')"
                                            :title="`点击复制: ${row.provide_volume || ''}`">
                                            {{ formatAccounting(row.provide_volume) }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="出发地" prop="provide_structure_name" width="250" sortable>
                                    <template #default="{ row }">
                                        <div class="copyable-cell"
                                            @click="copyCellContent(row.provide_structure_name, '出发地')"
                                            :title="`点击复制: ${row.provide_structure_name || ''}`">
                                            {{ row.provide_structure_name }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="目的地" prop="lack_structure_name" width="250" sortable>
                                    <template #default="{ row }">
                                        <div class="copyable-cell"
                                            @click="copyCellContent(row.lack_structure_name, '目的地')"
                                            :title="`点击复制: ${row.lack_structure_name || ''}`">
                                            {{ row.lack_structure_name }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="距离(Ly)" prop="provide_system_distance" width="100">
                                    <template #default="{ row }">
                                        <div class="copyable-cell"
                                            @click="copyCellContent(row.provide_system_distance, '距离')"
                                            :title="`点击复制: ${row.provide_system_distance || ''}`">
                                            {{ formatAccounting(row.provide_system_distance) }}
                                        </div>
                                    </template>
                                </el-table-column>
                            </KTable>
                        </KCard>
                    </div>
                </div>

                <!-- 小屏幕：图表和表格各自独占一行 -->
                <el-row v-else :gutter="20">
                    <el-col :span="24">
                        <KCard class="chart-card">
                            <template #header>
                                <span>物流关系图</span>
                            </template>
                            <div class="chart-wrapper">
                                <div ref="graphContainerRef" class="chart-container"></div>
                                <div v-if="!hasGraphData" class="chart-empty">
                                    <KEmpty why="当前计划没有可绘制的物流关系" size="sm" />
                                </div>
                            </div>
                        </KCard>
                    </el-col>
                    <el-col :span="24">
                        <KCard class="table-card">
                            <template #header>
                                <span>运力表</span>
                            </template>
                            <!-- 筛选器 -->
                            <div class="filter-container">
                                <el-select v-model="selectedDeparture" placeholder="请选择出发地" clearable
                                    style="width: 200px; margin-right: 10px;">
                                    <el-option v-for="item in departureFilterOptions" :key="item" :label="item"
                                        :value="item" />
                                </el-select>
                                <el-select v-model="selectedDestination" placeholder="请选择目的地" clearable
                                    style="width: 200px; margin-right: 10px;">
                                    <el-option v-for="item in destinationFilterOptions" :key="item" :label="item"
                                        :value="item" />
                                </el-select>
                                <el-button v-if="selectedDeparture || selectedDestination" type="primary" plain
                                    size="small" @click="clearFilters">
                                    清除筛选
                                </el-button>
                            </div>
                            <KTable class="k-report-table" :data="filteredTableData" show-summary :summary-method="volumeSummary" :key="`logistics-table-${selectedPlan || 'default'}`"
                                border max-height="600px">
                                <el-table-column label="icon" width="70">
                                    <template #default="{ row }">
                                        <img :src="`https://imageserver.eveonline.com/types/${row.lack_type_id}/icon`"
                                            alt="icon" width="40" height="40" style="object-fit: contain" loading="lazy" />
                                    </template>
                                </el-table-column>
                                <el-table-column label="物品名称" prop="lack_type_name" width="150">
                                    <template #default="{ row }">
                                        <div class="copyable-cell" @click="copyCellContent(row.lack_type_name, '物品名称')"
                                            :title="`点击复制: ${row.lack_type_name || ''}`">
                                            {{ row.lack_type_name }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="总数量" prop="provide_quantity" width="150">
                                    <template #default="{ row }">
                                        <div class="copyable-cell" @click="copyCellContent(row.provide_quantity, '总数量')"
                                            :title="`点击复制: ${row.provide_quantity || ''}`">
                                            {{ formatAccounting(row.provide_quantity) }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="总体积 (m³)" prop="provide_volume" width="150" align="right" sortable="custom">
                                    <template #header>
                                        <span>总体积 (m³)</span>
                                        <div
                                            style="font-size: 12px; color: #909399; font-weight: normal; margin-top: 4px;">
            
                                        </div>
                                    </template>
                                    <template #default="{ row }">
                                        <div class="copyable-cell" @click="copyCellContent(row.provide_volume, '总体积')"
                                            :title="`点击复制: ${row.provide_volume || ''}`">
                                            {{ formatAccounting(row.provide_volume) }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="出发地" prop="provide_structure_name" width="250" sortable>
                                    <template #default="{ row }">
                                        <div class="copyable-cell"
                                            @click="copyCellContent(row.provide_structure_name, '出发地')"
                                            :title="`点击复制: ${row.provide_structure_name || ''}`">
                                            {{ row.provide_structure_name }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="目的地" prop="lack_structure_name" width="250" sortable>
                                    <template #default="{ row }">
                                        <div class="copyable-cell"
                                            @click="copyCellContent(row.lack_structure_name, '目的地')"
                                            :title="`点击复制: ${row.lack_structure_name || ''}`">
                                            {{ row.lack_structure_name }}
                                        </div>
                                    </template>
                                </el-table-column>
                                <el-table-column label="距离(Ly)" prop="provide_system_distance" width="100">
                                    <template #default="{ row }">
                                        <div class="copyable-cell"
                                            @click="copyCellContent(row.provide_system_distance, '距离')"
                                            :title="`点击复制: ${row.provide_system_distance || ''}`">
                                            {{ formatAccounting(row.provide_system_distance) }}
                                        </div>
                                    </template>
                                </el-table-column>
                            </KTable>
                        </KCard>
                    </el-col>
                </el-row>
            </div>
        </KCard>
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
    color: var(--k-color-text-tertiary);
}

.content-container {
    padding: 0;
}

/* 分割容器样式 - 大屏幕时使用 */
.split-container {
    display: flex;
    width: 100%;
    height: 62vh;
    min-height: 320px;
    position: relative;
}

.split-pane {
    height: 100%;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.chart-pane {
    flex-shrink: 0;
}

.table-pane {
    flex-shrink: 0;
}

/* 分割线样式 */
.split-divider {
    width: 4px;
    background-color: var(--k-color-border);
    cursor: col-resize;
    position: relative;
    flex-shrink: 0;
    user-select: none;
    transition: background-color 0.2s;
}

.split-divider:hover {
    background-color: var(--k-color-primary);
}

.split-divider.dragging {
    background-color: var(--k-color-primary);
}

.split-handle {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 20px;
    height: 40px;
    background-color: var(--k-color-border);
    border-radius: var(--k-radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
}

.split-handle::before,
.split-handle::after {
    content: '';
    position: absolute;
    width: 2px;
    height: 12px;
    background-color: var(--k-color-text-secondary);
    left: 50%;
    transform: translateX(-50%);
}

.split-handle::before {
    left: calc(50% - 4px);
}

.split-handle::after {
    left: calc(50% + 4px);
}

.split-divider:hover .split-handle,
.split-divider.dragging .split-handle {
    background-color: var(--k-color-primary);
}

.split-divider:hover .split-handle::before,
.split-divider:hover .split-handle::after,
.split-divider.dragging .split-handle::before,
.split-divider.dragging .split-handle::after {
    background-color: var(--k-color-text-inverse);
}

.chart-card {
    margin-bottom: 0;
    height: 100%;
    display: flex;
    flex-direction: column;
}

.chart-card :deep(.k-card__body) {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 20px;
}

.table-card {
    height: 100%;
    display: flex;
    flex-direction: column;
    margin-left: 0;
}

.table-card :deep(.k-card__body) {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 20px;
}

.filter-container {
    display: flex;
    align-items: center;
    margin-bottom: 15px;
    flex-wrap: wrap;
    gap: 10px;
}

/* 小屏幕时的样式 */
@media (max-width: 1919px) {
    .chart-card {
        margin-bottom: 20px;
    }

    .chart-card :deep(.k-card__body) {
        padding: 20px;
    }

    .table-card {
        margin-left: 0;
    }

    .chart-container {
        height: 58vh;
        min-height: 240px;
    }
}

/* 图表容器外套一层，用于在无数据时叠一个空态提示 */
.chart-wrapper {
    position: relative;
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
}

.chart-empty {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--k-color-surface);
}

.chart-container {
    width: 100%;
    height: 100%;
    min-height: 240px;
    flex: 1;
}

.copyable-cell {
    cursor: pointer;
    user-select: none;
}
</style>
