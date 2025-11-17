<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'

// 定义接口类型
interface childMaterial {
    index_id: number
    quantity: number
    jita_buy_price: number
    type_id: number
    type_name: string
    material_type_node?: string
}

interface topProduct {
    children: childMaterial[]
    eiv_cost: number
    index_id: number
    type_id: number
    type_name: string
    product_num: number
}

// Props定义：接收的数据可能是对象（字典）或数组
const props = defineProps<{
    PlanCalculateEIVCostTableView: any
}>()

// 数据预处理：将传入的数据标准化为topProduct数组
const topProducts = computed<topProduct[]>(() => {
    const data = props.PlanCalculateEIVCostTableView
    
    if (!data) {
        return []
    }
    
    // 如果是数组，直接返回
    if (Array.isArray(data)) {
        // 如果数组元素是对象且包含topProducts属性
        if (data.length > 0 && data[0] && typeof data[0] === 'object' && 'topProducts' in data[0]) {
            return data[0].topProducts || []
        }
        // 如果数组元素本身就是topProduct格式
        return data as topProduct[]
    }
    
    // 如果是对象（字典），转换为数组
    if (typeof data === 'object') {
        // 如果对象包含topProducts属性
        if ('topProducts' in data && Array.isArray(data.topProducts)) {
            return data.topProducts
        }
        // 如果是字典格式（key为type_id），转换为数组
        return Object.values(data) as topProduct[]
    }
    
    return []
})

// 维度1：最终产品维度汇总
interface ProductCostSummary {
    type_id: number
    type_name: string
    total_cost: number
    children_cost: number
    eiv_cost: number
    percentage: number
}

const productCostSummary = computed<ProductCostSummary[]>(() => {
    const products = topProducts.value
    if (!products || products.length === 0) {
        return []
    }
    
    // 计算每个产品的总成本
    const summaries: ProductCostSummary[] = products.map(product => {
        // 计算children的总成本
        const childrenCost = (product.children || []).reduce((sum, child) => {
            const quantity = child.quantity || 0
            const price = child.jita_buy_price || 0
            return sum + (quantity * price)
        }, 0)
        
        // 总成本 = children成本 + eiv_cost
        const totalCost = childrenCost + (product.eiv_cost || 0)
        
        return {
            type_id: product.type_id,
            type_name: product.type_name || '',
            total_cost: totalCost,
            children_cost: childrenCost,
            eiv_cost: product.eiv_cost || 0,
            product_num: product.product_num || 0,
            percentage: 0 // 稍后计算
        }
    })
    
    // 计算总成本
    const totalCost = summaries.reduce((sum, item) => sum + item.total_cost, 0)
    
    // 计算每个产品的比例
    if (totalCost > 0) {
        summaries.forEach(item => {
            item.percentage = (item.total_cost / totalCost) * 100
        })
    }
    
    // 按总成本降序排序
    return summaries.sort((a, b) => b.total_cost - a.total_cost)
})

// 维度2：children种类维度汇总
interface CategoryCostSummary {
    category: string
    total_cost: number
    percentage: number
}

const categoryCostSummary = computed<CategoryCostSummary[]>(() => {
    const products = topProducts.value
    if (!products || products.length === 0) {
        return []
    }
    
    // 按material_type_node分类汇总
    const categoryMap = new Map<string, number>()
    let totalEivCost = 0
    
    products.forEach(product => {
        // 汇总eiv_cost
        totalEivCost += product.eiv_cost || 0
        
        // 汇总children按material_type_node分类
        if (product.children && product.children.length > 0) {
            product.children.forEach(child => {
                const category = child.material_type_node || '未知分类'
                const cost = (child.quantity || 0) * (child.jita_buy_price || 0)
                
                if (categoryMap.has(category)) {
                    categoryMap.set(category, categoryMap.get(category)! + cost)
                } else {
                    categoryMap.set(category, cost)
                }
            })
        }
    })
    
    // 转换为数组
    const summaries: CategoryCostSummary[] = []
    
    // 添加material_type_node分类
    categoryMap.forEach((cost, category) => {
        summaries.push({
            category,
            total_cost: cost,
            percentage: 0 // 稍后计算
        })
    })
    
    // 添加eiv_cost分类
    if (totalEivCost > 0) {
        summaries.push({
            category: 'EIV成本',
            total_cost: totalEivCost,
            percentage: 0 // 稍后计算
        })
    }
    
    // 计算总成本
    const totalCost = summaries.reduce((sum, item) => sum + item.total_cost, 0)
    
    // 计算每个分类的比例
    if (totalCost > 0) {
        summaries.forEach(item => {
            item.percentage = (item.total_cost / totalCost) * 100
        })
    }
    
    // 按总成本降序排序
    return summaries.sort((a, b) => b.total_cost - a.total_cost)
})

// 格式化数字（千分位）
const formatNumber = (value: number): string => {
    if (value === null || value === undefined || isNaN(value)) {
        return '0'
    }
    return value.toLocaleString('zh-CN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    })
}

// 格式化百分比
const formatPercentage = (value: number): string => {
    if (value === null || value === undefined || isNaN(value)) {
        return '0.00%'
    }
    return `${value.toFixed(2)}%`
}

// 图表引用
const productChartRef = ref<HTMLElement>()
const categoryChartRef = ref<HTMLElement>()
let productChartInstance: echarts.ECharts | null = null
let categoryChartInstance: echarts.ECharts | null = null

// 初始化产品维度饼图
const initProductChart = () => {
    if (!productChartRef.value) return
    
    const data = productCostSummary.value
    if (!data || data.length === 0) {
        if (productChartInstance) {
            productChartInstance.dispose()
            productChartInstance = null
        }
        return
    }
    
    if (!productChartInstance) {
        productChartInstance = echarts.init(productChartRef.value)
    }
    
    const chartData = data.map(item => ({
        name: item.type_name,
        value: item.total_cost
    }))
    
    const total = data.reduce((sum, item) => sum + item.total_cost, 0)
    
    const option: EChartsOption = {
        title: {
            text: '最终产品成本占比',
            left: 'center',
            textStyle: {
                fontSize: 16
            }
        },
        tooltip: {
            trigger: 'item',
            formatter: (params: any) => {
                const percentage = ((params.value / total) * 100).toFixed(2)
                return `${params.name}<br/>成本: ${formatNumber(params.value)}<br/>占比: ${percentage}%`
            }
        },
        legend: {
            orient: 'vertical',
            left: 'left',
            top: 'middle'
        },
        series: [
            {
                name: '产品成本',
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
    
    productChartInstance.setOption(option, true) // 使用 notMerge=true 确保完全更新
    // 确保图表正确渲染
    productChartInstance.resize()
}

// 初始化分类维度饼图
const initCategoryChart = () => {
    if (!categoryChartRef.value) return
    
    const data = categoryCostSummary.value
    if (!data || data.length === 0) {
        if (categoryChartInstance) {
            categoryChartInstance.dispose()
            categoryChartInstance = null
        }
        return
    }
    
    if (!categoryChartInstance) {
        categoryChartInstance = echarts.init(categoryChartRef.value)
    }
    
    const chartData = data.map(item => ({
        name: item.category,
        value: item.total_cost
    }))
    
    const total = data.reduce((sum, item) => sum + item.total_cost, 0)
    
    const option: EChartsOption = {
        title: {
            text: '材料分类成本占比',
            left: 'center',
            textStyle: {
                fontSize: 16
            }
        },
        tooltip: {
            trigger: 'item',
            formatter: (params: any) => {
                const percentage = ((params.value / total) * 100).toFixed(2)
                return `${params.name}<br/>成本: ${formatNumber(params.value)}<br/>占比: ${percentage}%`
            }
        },
        legend: {
            orient: 'vertical',
            left: 'left',
            top: 'middle'
        },
        series: [
            {
                name: '分类成本',
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
    
    categoryChartInstance.setOption(option, true) // 使用 notMerge=true 确保完全更新
    // 确保图表正确渲染
    categoryChartInstance.resize()
}

// 更新图表
const updateCharts = async () => {
    await nextTick()
    if (productChartRef.value && categoryChartRef.value) {
        const productContainer = productChartRef.value
        const categoryContainer = categoryChartRef.value
        
        if (productContainer.offsetWidth > 0 && categoryContainer.offsetWidth > 0) {
            initProductChart()
            initCategoryChart()
        } else {
            setTimeout(() => {
                if (productContainer.offsetWidth > 0 && categoryContainer.offsetWidth > 0) {
                    initProductChart()
                    initCategoryChart()
                } else {
                    setTimeout(() => {
                        initProductChart()
                        initCategoryChart()
                    }, 200)
                }
            }, 100)
        }
    }
}

// 监听数据变化
watch(() => props.PlanCalculateEIVCostTableView, () => {
    updateCharts()
}, { deep: true, immediate: false })

watch(productCostSummary, () => {
    if (productCostSummary.value && productCostSummary.value.length > 0) {
        updateCharts()
    }
}, { deep: true, immediate: false })

watch(categoryCostSummary, () => {
    if (categoryCostSummary.value && categoryCostSummary.value.length > 0) {
        updateCharts()
    }
}, { deep: true, immediate: false })

// 监听容器尺寸变化，确保图表能正确初始化
const observeContainer = () => {
    if (productChartRef.value && categoryChartRef.value) {
        const observer = new ResizeObserver(() => {
            // 当容器尺寸变化时，如果图表已初始化，重新调整大小
            if (productChartInstance) {
                productChartInstance.resize()
            }
            if (categoryChartInstance) {
                categoryChartInstance.resize()
            }
        })
        
        observer.observe(productChartRef.value)
        observer.observe(categoryChartRef.value)
        
        return observer
    }
    return null
}

// 窗口大小调整处理函数
const handleResize = () => {
    productChartInstance?.resize()
    categoryChartInstance?.resize()
}

// ResizeObserver 实例
let containerObserver: ResizeObserver | null = null

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
        updateCharts()
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
    if (productChartInstance) {
        productChartInstance.dispose()
        productChartInstance = null
    }
    if (categoryChartInstance) {
        categoryChartInstance.dispose()
        categoryChartInstance = null
    }
    // 移除事件监听
    window.removeEventListener('resize', handleResize)
})

</script>

<template>
    <div class="cost-view">
        <el-row :gutter="20">
            <!-- 维度1：最终产品维度 -->
            <el-col :span="12">
                <el-card class="cost-card">
                    <template #header>
                        <div class="card-header">
                            <span>最终产品成本汇总</span>
                        </div>
                    </template>
                    <el-table
                        :data="productCostSummary"
                        stripe
                        border
                        style="width: 100%"
                        :max-height="400"
                    >
                        <el-table-column prop="type_name" label="产品名称" width="200" />
                        <el-table-column prop="total_cost" label="生产数量" width="150">
                            <template #default="{ row }">
                                <strong>{{ formatNumber(row.product_num) }}</strong>
                            </template>
                        </el-table-column>
                        <el-table-column prop="children_cost" label="材料成本" width="150">
                            <template #default="{ row }">
                                {{ formatNumber(row.children_cost) }}
                            </template>
                        </el-table-column>
                        <el-table-column prop="eiv_cost" label="EIV成本" width="150">
                            <template #default="{ row }">
                                {{ formatNumber(row.eiv_cost) }}
                            </template>
                        </el-table-column>
                        <el-table-column prop="total_cost" label="总成本" width="150">
                            <template #default="{ row }">
                                <strong>{{ formatNumber(row.total_cost) }}</strong>
                            </template>
                        </el-table-column>
                        <el-table-column prop="total_cost" label="单位成本" width="150">
                            <template #default="{ row }">
                                <strong>{{ formatNumber(row.total_cost / row.product_num) }}</strong>
                            </template>
                        </el-table-column>
                        <el-table-column prop="percentage" label="占比" width="100">
                            <template #default="{ row }">
                                {{ formatPercentage(row.percentage) }}
                            </template>
                        </el-table-column>
                    </el-table>
                    <div ref="productChartRef" style="width: 100%; height: 400px; margin-top: 20px;"></div>
                </el-card>
            </el-col>
            
            <!-- 维度2：分类维度 -->
            <el-col :span="12">
                <el-card class="cost-card">
                    <template #header>
                        <div class="card-header">
                            <span>材料分类成本汇总</span>
                        </div>
                    </template>
                    <el-table
                        :data="categoryCostSummary"
                        stripe
                        border
                        style="width: 100%"
                        :max-height="400"
                    >
                        <el-table-column prop="category" label="分类" width="200" />
                        <el-table-column prop="total_cost" label="总成本" width="200">
                            <template #default="{ row }">
                                <strong>{{ formatNumber(row.total_cost) }}</strong>
                            </template>
                        </el-table-column>
                        <el-table-column prop="percentage" label="占比" width="150">
                            <template #default="{ row }">
                                {{ formatPercentage(row.percentage) }}
                            </template>
                        </el-table-column>
                    </el-table>
                    <div ref="categoryChartRef" style="width: 100%; height: 400px; margin-top: 20px;"></div>
                </el-card>
            </el-col>
        </el-row>
    </div>
</template>

<style scoped>
.cost-view {
    padding: 20px;
}

.cost-card {
    margin-bottom: 20px;
}

.card-header {
    font-size: 16px;
    font-weight: bold;
}

:deep(.el-table) {
    font-size: 14px;
}

:deep(.el-table th) {
    background-color: #f5f7fa;
    font-weight: bold;
}
</style>