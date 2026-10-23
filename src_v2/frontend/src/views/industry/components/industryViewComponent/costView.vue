<script setup lang="ts">
import KTable from '@/components/k/KTable.vue'
import KCard from '@/components/k/KCard.vue'
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { useAuthStore } from '@/stores/auth'
import { http } from '@/http'
import { useEdition } from '@/composables/useEdition'
import { getChartThemeColors, themedTooltip, onThemeTokenChange } from '@/utils/echartsTheme'

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
    blueprint_cost?: number
    index_id: number
    type_id: number
    type_name: string
    product_num: number
    tax_items?: Array<{ category?: string; name?: string; target_category?: string; tax_rate?: number; rate?: number; tax_amount?: number; amount?: number }>
}

// Props定义：接收的数据可能是对象（字典）或数组
const props = defineProps<{
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- 后端成本表在「数组 / 字典」两种形态间切换，沿用历史契约
    PlanCalculateEIVCostTableView: any
}>()

// 权限检查
const authStore = useAuthStore()
// 版本检查（社区版没有企业版市场接口）
const { isEnterprise } = useEdition()
const hasOmegaSubscription = computed(() => {
    return authStore.user?.roles.includes('vip_omega') || false
})

// 产品价格数据
const productPrices = ref<Record<number, { jita_buy_price: number; jita_sell_price: number }>>({})
const loadingPrices = ref(false)

// 数据预处理：将传入的数据标准化为topProduct数组
const topProducts = computed<topProduct[]>(() => {
    const data = props.PlanCalculateEIVCostTableView

    if (!data) {
        return []
    }

    let result: topProduct[] = []
    
    // 如果是数组，直接返回
    if (Array.isArray(data)) {
        // 如果数组元素是对象且包含topProducts属性
        if (data.length> 0 && data[0] && typeof data[0] === 'object' && 'topProducts' in data[0]) {
            result = data[0].topProducts || []
        } else {
            // 如果数组元素本身就是topProduct格式
            result = data as topProduct[]
        }
    } else if (typeof data === 'object') {
        // 如果是对象（字典），转换为数组
        // 如果对象包含topProducts属性
        if ('topProducts' in data && Array.isArray(data.topProducts)) {
            result = data.topProducts
        } else {
            // 如果是字典格式（key为type_id），转换为数组
            result = Object.values(data) as topProduct[]
        }
    }
    
    return result
})

// 维度1：最终产品维度汇总
interface ProductCostSummary {
    type_id: number
    type_name: string
    total_cost: number
    children_cost: number
    eiv_cost: number
    blueprint_cost: number
    percentage: number
    product_num: number
    expected_profit?: number
    expected_profit_per_unit?: number
}

const productCostSummary = computed<ProductCostSummary[]>(() => {
    const products = topProducts.value
    if (!products || products.length === 0) {
        return []
    }

    // 按 type_id 分组，合并相同产品
    const productMap = new Map<number, {
        type_id: number
        type_name: string
        product_num: number
        eiv_cost: number
        blueprint_cost: number
        children: Map<number, childMaterial> // 使用 Map 按 type_id 合并相同材料
    }>()

    // 遍历所有产品，按 type_id 分组并合并
    products.forEach(product => {
        const typeId = product.type_id
        const existing = productMap.get(typeId)

        if (existing) {
            // 如果已存在相同 type_id 的产品，合并数据
            const newProductNum = Number(product.product_num) || 0
            existing.product_num = Number(existing.product_num) + newProductNum
            existing.eiv_cost += product.eiv_cost || 0
            existing.blueprint_cost += product.blueprint_cost || 0

            // 合并 children 材料
            if (product.children && product.children.length> 0) {
                product.children.forEach(child => {
                    // 使用 type_id 作为唯一标识，因为成本视图关注的是材料类型和总数量
                    const childKey = child.type_id
                    const existingChild = existing.children.get(childKey)

                    if (existingChild) {
                        // 如果材料已存在，累加数量
                        existingChild.quantity = (existingChild.quantity || 0) + (child.quantity || 0)
                    } else {
                        // 如果材料不存在，添加新材料（需要深拷贝避免引用问题）
                        existing.children.set(childKey, {
                            ...child,
                            quantity: child.quantity || 0
                        })
                    }
                })
            }
        } else {
            // 如果不存在，创建新条目
            const childrenMap = new Map<number, childMaterial>()
            if (product.children && product.children.length> 0) {
                product.children.forEach(child => {
                    // 使用 type_id 作为唯一标识
                    const childKey = child.type_id
                    childrenMap.set(childKey, {
                        ...child,
                        quantity: child.quantity || 0
                    })
                })
            }

            productMap.set(typeId, {
                type_id: typeId,
                type_name: product.type_name || '',
                product_num: Number(product.product_num) || 0,
                eiv_cost: product.eiv_cost || 0,
                blueprint_cost: product.blueprint_cost || 0,
                children: childrenMap
            })
        }
    })

    // 将合并后的数据转换为 ProductCostSummary 数组
    const summaries: ProductCostSummary[] = Array.from(productMap.values()).map(mergedProduct => {
        // 将 children Map 转换为数组
        const childrenArray = Array.from(mergedProduct.children.values())

        // 计算children的总成本
        const childrenCost = childrenArray.reduce((sum, child) => {
            const quantity = child.quantity || 0
            const price = child.jita_buy_price || 0
            return sum + (quantity * price)
        }, 0)

        // 总成本 = children成本 + eiv_cost + blueprint_cost
        const totalCost = childrenCost + mergedProduct.eiv_cost + (mergedProduct.blueprint_cost || 0)

        return {
            type_id: mergedProduct.type_id,
            type_name: mergedProduct.type_name,
            total_cost: totalCost,
            children_cost: childrenCost,
            eiv_cost: mergedProduct.eiv_cost,
            blueprint_cost: mergedProduct.blueprint_cost,
            product_num: mergedProduct.product_num,
            percentage: 0 // 稍后计算
        }
    })

    // 计算总成本
    const totalCost = summaries.reduce((sum, item) => sum + item.total_cost, 0)

    // 计算每个产品的比例
    if (totalCost> 0) {
        summaries.forEach(item => {
            item.percentage = (item.total_cost / totalCost) * 100
        })
    }

    // 计算预期利润（仅omega用户）
    if (hasOmegaSubscription.value) {
        summaries.forEach(item => {
            const priceData = productPrices.value[item.type_id]
            if (priceData && priceData.jita_buy_price> 0) {
                // 预期利润 = (jita_buy_price * product_num) - total_cost
                const totalRevenue = priceData.jita_buy_price * item.product_num
                item.expected_profit = totalRevenue - item.total_cost
                // 单个产品预期利润
                if (item.product_num> 0) {
                    item.expected_profit_per_unit = item.expected_profit / item.product_num
                } else {
                    item.expected_profit_per_unit = 0
                }
            } else {
                // 如果没有价格数据，设置为undefined（显示加载中）
                item.expected_profit = undefined
                item.expected_profit_per_unit = undefined
            }
        })
    }

    // 按总成本降序排序
    return summaries.sort((a, b) => b.total_cost - a.total_cost)
})

// 计算汇总值
const expectedProfitTotal = computed(() => {
    if (!hasOmegaSubscription.value) {
        return 0
    }
    return productCostSummary.value.reduce((sum, row) => {
        if (row.expected_profit !== undefined && !isNaN(row.expected_profit)) {
            return sum + row.expected_profit
        }
        return sum
    }, 0)
})

const totalCostSum = computed(() => {
    const productTotal = productCostSummary.value.reduce((sum, row) => sum + (row.total_cost || 0), 0)
    // 计入所有产品的税费（蓝图成本已在 productTotal 中）
    const taxTotal = topProducts.value.reduce((sum, p) => {
        return sum + (p.tax_items || []).reduce((s: number, t: NonNullable<topProduct['tax_items']>[number]) => s + (t.tax_amount ?? t.amount ?? 0), 0)
    }, 0)
    return productTotal + taxTotal
})

const childrenCostSum = computed(() => {
    return productCostSummary.value.reduce((sum, row) => sum + (row.children_cost || 0), 0)
})

const eivCostSum = computed(() => {
    return productCostSummary.value.reduce((sum, row) => sum + (row.eiv_cost || 0), 0)
})

const blueprintCostSum = computed(() => {
    return productCostSummary.value.reduce((sum, row) => sum + (row.blueprint_cost || 0), 0)
})

const productNumSum = computed(() => {
    return productCostSummary.value.reduce((sum, row) => sum + (row.product_num || 0), 0)
})

// 获取产品价格
const fetchProductPrices = async () => {
    // 防御性守卫：社区版没有 /enterprise/market/product_prices 接口，直接拦截，避免 404 噪音
    if (!isEnterprise) {
        return
    }

    if (!hasOmegaSubscription.value) {
        return
    }

    const products = topProducts.value
    if (!products || products.length === 0) {
        return
    }

    // 提取所有产品的type_id
    const typeIds = products.map(p => p.type_id).filter(id => id> 0)
    if (typeIds.length === 0) {
        return
    }

    loadingPrices.value = true
    try {
        const res = await http.post('/enterprise/market/product_prices', {
            type_ids: typeIds
        })

        if (!res.ok) {
            console.error('获取产品价格失败:', res.status)
            return
        }

        const data = await res.json()
        if (data.status === 200 && data.data) {
            productPrices.value = data.data
        }
    } catch (error) {
        console.error('获取产品价格失败:', error)
    } finally {
        loadingPrices.value = false
    }
}

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
    let totalBlueprintCost = 0

    products.forEach(product => {
        // 汇总eiv_cost
        totalEivCost += product.eiv_cost || 0

        // 汇总blueprint_cost
        totalBlueprintCost += product.blueprint_cost || 0

        // 汇总children按material_type_node分类
        if (product.children && product.children.length> 0) {
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
    if (totalEivCost> 0) {
        summaries.push({
            category: 'EIV成本',
            total_cost: totalEivCost,
            percentage: 0 // 稍后计算
        })
    }

    // 添加blueprint_cost分类
    if (totalBlueprintCost > 0) {
        summaries.push({
            category: '蓝图成本',
            total_cost: totalBlueprintCost,
            percentage: 0 // 稍后计算
        })
    }

    // 处理 tax_items：按分类汇总税费
    const taxMap = new Map<string, number>()
    products.forEach(product => {
        const taxItems = product.tax_items
        if (taxItems && Array.isArray(taxItems)) {
            taxItems.forEach((item: NonNullable<topProduct['tax_items']>[number]) => {
                const category = item.category || item.name || ''
                const amount = item.tax_amount ?? item.amount ?? 0
                if (category && amount > 0) {
                    taxMap.set(category, (taxMap.get(category) || 0) + amount)
                }
            })
        }
    })
    taxMap.forEach((amount, category) => {
        summaries.push({
            category,
            total_cost: amount,
            percentage: 0 // 稍后计算
        })
    })

    // 计算总成本
    const totalCost = summaries.reduce((sum, item) => sum + item.total_cost, 0)

    // 计算每个分类的比例
    if (totalCost> 0) {
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

// 表格汇总方法
const getSummaries = (param: { columns: Array<{ property?: string; label?: string }>, data: ProductCostSummary[] }) => {
    const { columns } = param
    const sums: string[] = []

    columns.forEach((column, index) => {
        if (index === 0) {
            // 第一列：产品名称，显示"合计"
            sums.push('合计')
        } else if (column.label === '数量') {
            // 数量列：显示总数量
            sums.push(String(productNumSum.value))
        } else if (column.property === 'expected_profit') {
            // 预期利润列：计算总和
            if (hasOmegaSubscription.value) {
                sums.push(formatNumber(expectedProfitTotal.value))
            } else {
                sums.push('')
            }
        } else if (column.label === '总成本') {
            // 总成本列：计算总和
            sums.push(formatNumber(totalCostSum.value))
        } else if (column.property === 'children_cost') {
            // 材料成本列：计算总和
            sums.push(formatNumber(childrenCostSum.value))
        } else if (column.property === 'eiv_cost') {
            // EIV成本列：计算总和
            sums.push(formatNumber(eivCostSum.value))
        } else if (column.property === 'blueprint_cost') {
            // 蓝图成本列：计算总和
            sums.push(formatNumber(blueprintCostSum.value))
        } else {
            sums.push('')
        }
    })

    return sums
}

// 材料分类成本汇总：合计总成本与占比
const getCategorySummaries = (param: { columns: Array<{ property?: string, label?: string }>, data: Array<Record<string, unknown>> }) => {
    const { columns, data } = param
    const total = (data || []).reduce((s: number, row: Record<string, unknown>) => s + (Number(row?.total_cost) || 0), 0)
    return columns.map((column: { property?: string, label?: string }, index: number) => {
        if (index === 0) return '合计'
        if (column.property === 'total_cost') return formatNumber(total)
        if (column.property === 'percentage') return total > 0 ? '100.00%' : '-'
        return ''
    })
}
// 图表引用
const productChartRef = ref<HTMLElement>()
const categoryChartRef = ref<HTMLElement>()
let productChartInstance: echarts.ECharts | null = null
let categoryChartInstance: echarts.ECharts | null = null
let cleanupThemeWatcher: (() => void) | null = null

// 初始化产品维度饼图
const initProductChart = () => {
    const c = getChartThemeColors()
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
        // 同上：标题交给卡片头部，图内只留图形与标签
        tooltip: {
            ...themedTooltip(c),
            trigger: 'item',
            formatter: (params) => {
                const p = Array.isArray(params) ? params[0] : params
                const value = Number(p.value)
                const percentage = ((value / total) * 100).toFixed(2)
                return `${p.name}<br/>成本: ${formatNumber(value)}<br/>占比: ${percentage}%`
            }
        },
        legend: {
            orient: 'vertical',
            left: 'left',
            top: 'middle',
            textStyle: { color: c.textSecondary }
        },
        series: [
            {
                name: '产品成本',
                type: 'pie',
                radius: ['40%', '70%'],
                avoidLabelOverlap: true,
                itemStyle: {
                    borderRadius: 10,
                    borderColor: c.surface,
                    borderWidth: 2
                },
                label: {
                    show: true,
                    color: c.text,
                    formatter: (params) => {
                        const percentage = ((Number(params.value) / total) * 100).toFixed(1)
                        return `${params.name}\n${percentage}%`
                    }
                },
                emphasis: {
                    label: {
                        show: true,
                        fontSize: 16,
                        fontWeight: 'bold',
                        color: c.text
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
    const c = getChartThemeColors()
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
        // 标题由外层卡片头部提供，图内不再重复画一遍（否则两行标题和扇区标签叠在一起）
        tooltip: {
            ...themedTooltip(c),
            trigger: 'item',
            formatter: (params) => {
                const p = Array.isArray(params) ? params[0] : params
                const value = Number(p.value)
                const percentage = ((value / total) * 100).toFixed(2)
                return `${p.name}<br/>成本: ${formatNumber(value)}<br/>占比: ${percentage}%`
            }
        },
        legend: {
            orient: 'vertical',
            left: 'left',
            top: 'middle',
            textStyle: { color: c.textSecondary }
        },
        series: [
            {
                name: '分类成本',
                type: 'pie',
                radius: ['40%', '70%'],
                avoidLabelOverlap: true,
                itemStyle: {
                    borderRadius: 10,
                    borderColor: c.surface,
                    borderWidth: 2
                },
                label: {
                    show: true,
                    color: c.text,
                    formatter: (params) => {
                        const percentage = ((Number(params.value) / total) * 100).toFixed(1)
                        return `${params.name}\n${percentage}%`
                    }
                },
                emphasis: {
                    label: {
                        show: true,
                        fontSize: 16,
                        fontWeight: 'bold',
                        color: c.text
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

        if (productContainer.offsetWidth> 0 && categoryContainer.offsetWidth> 0) {
            initProductChart()
            initCategoryChart()
        } else {
            setTimeout(() => {
                if (productContainer.offsetWidth> 0 && categoryContainer.offsetWidth> 0) {
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
    // 如果是omega用户，自动获取产品价格
    if (hasOmegaSubscription.value) {
        fetchProductPrices()
    }
}, { deep: true, immediate: false })

watch(productCostSummary, () => {
    if (productCostSummary.value && productCostSummary.value.length> 0) {
        updateCharts()
    }
}, { deep: true, immediate: false })

watch(categoryCostSummary, () => {
    if (categoryCostSummary.value && categoryCostSummary.value.length> 0) {
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

// 窗口大小调整处理函数 (RAF throttle)
let resizeRAF: number | null = null
const handleResize = () => {
  if (resizeRAF !== null) return
  resizeRAF = requestAnimationFrame(() => {
    productChartInstance?.resize()
    categoryChartInstance?.resize()
    resizeRAF = null
  })
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

    // 如果是omega用户，获取产品价格
    if (hasOmegaSubscription.value) {
        fetchProductPrices()
    }

    // 响应式调整图表大小
    window.addEventListener('resize', handleResize)
    cleanupThemeWatcher = onThemeTokenChange(() => {
        updateCharts()
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
    if (productChartInstance) {
        productChartInstance.dispose()
        productChartInstance = null
    }
    if (categoryChartInstance) {
        categoryChartInstance.dispose()
        categoryChartInstance = null
    }
    // 移除事件监听
    if (resizeRAF !== null) cancelAnimationFrame(resizeRAF)
    window.removeEventListener('resize', handleResize)

    cleanupThemeWatcher?.()
    cleanupThemeWatcher = null
})

</script>

<template>
    <div class="cost-view">
        <el-row :gutter="20">
            <!-- 维度1：最终产品维度 -->
            <el-col :span="12">
                <!-- 图表卡片 -->
                <KCard class="cost-card" title="最终产品成本占比">
                    <div ref="productChartRef" style="width: 100%; height: 400px;"></div>
                </KCard>
            </el-col>
            <el-col :span="12">
                <!-- 图表卡片 -->
                <KCard class="cost-card" title="材料分类成本占比">
                    <div ref="categoryChartRef" style="width: 100%; height: 400px;"></div>
                </KCard>
            </el-col>
        </el-row>
        <el-row :gutter="20">
            <el-col :span="17">
                <!-- 表格卡片 -->
                <KCard class="cost-card" title="最终产品成本汇总">
                    <KTable class="k-report-table" :data="productCostSummary" style="width: 100%" show-summary :summary-method="getSummaries">
                        <el-table-column prop="type_name" label="产品名称" min-width="150" show-overflow-tooltip />
                        <el-table-column prop="product_num" label="数量" width="90" align="right" sortable>
                        <template #default="{ row }">
                            {{ row.product_num }}
                        </template>
                    </el-table-column>
                        <el-table-column v-if="hasOmegaSubscription" prop="expected_profit" label="预期利润" width="150" align="right" sortable>
                        <template #default="{ row }">
                            <div v-if="row.expected_profit !== undefined" class="cost-cell"
                                :class="row.expected_profit >= 0 ? 'num-good' : 'num-danger'">
                                <span class="cost-main">{{ formatNumber(row.expected_profit) }}</span>
                                <span v-if="row.product_num > 1" class="cost-sub">
                                    {{ formatNumber(row.expected_profit_per_unit || 0) }}/per
                                </span>
                            </div>
                            <span v-else class="num-muted">加载中...</span>
                        </template>
                        <template #summary>
                            <div v-if="hasOmegaSubscription"
                                :style="{ color: expectedProfitTotal > 0 ? 'var(--k-color-success)' : expectedProfitTotal < 0 ? 'var(--k-color-danger)' : 'var(--k-color-text-secondary)', fontWeight: 'bold' }">
                                {{ formatNumber(expectedProfitTotal) }}
                            </div>
                            <div v-else></div>
                        </template>
                    </el-table-column>
                        <el-table-column prop="total_cost" label="总成本" width="160" align="right" sortable>
                            <template #default="{ row }">
                                <div class="cost-cell">
                                    <span class="cost-main">{{ formatNumber(row.total_cost) }}</span>
                                    <span class="cost-sub">{{ formatPercentage(row.percentage) }}</span>
                                    <span v-if="row.product_num > 1" class="cost-sub">
                                        {{ formatNumber(row.total_cost / row.product_num) }}/per
                                    </span>
                                </div>
                            </template>
                        </el-table-column>
                        <el-table-column prop="children_cost" label="材料成本" width="160" align="right" sortable>
                        <template #default="{ row }">
                            <div class="cost-cell">
                                <span class="cost-main">{{ formatNumber(row.children_cost) }}</span>
                                <span v-if="row.product_num > 1" class="cost-sub">
                                    {{ formatNumber(row.children_cost / row.product_num) }}/per
                                </span>
                            </div>
                        </template>
                    </el-table-column>
                        <el-table-column prop="eiv_cost" label="EIV成本" width="150" align="right" sortable>
                        <template #default="{ row }">
                            <div class="cost-cell">
                                <span class="cost-main">{{ formatNumber(row.eiv_cost) }}</span>
                                <span v-if="row.product_num > 1" class="cost-sub">
                                    {{ formatNumber(row.eiv_cost / row.product_num) }}/per
                                </span>
                            </div>
                        </template>
                    </el-table-column>
                        <el-table-column prop="blueprint_cost" label="蓝图成本" width="150" align="right" sortable>
                        <template #default="{ row }">
                            <div class="cost-cell">
                                <span class="cost-main">{{ formatNumber(row.blueprint_cost || 0) }}</span>
                                <span v-if="row.product_num > 1" class="cost-sub">
                                    {{ formatNumber((row.blueprint_cost || 0) / row.product_num) }}/per
                                </span>
                            </div>
                        </template>
                    </el-table-column>
                    </KTable>
                </KCard>
            </el-col>
            <!-- 维度2：分类维度 -->
            <el-col :span="7">
                <!-- 表格卡片 -->
                <KCard class="cost-card" title="材料分类成本汇总">
                    <KTable class="k-report-table" :data="categoryCostSummary" style="width: 100%" show-summary :summary-method="getCategorySummaries">
                        <el-table-column prop="category" label="分类" min-width="110" show-overflow-tooltip />
                        <el-table-column prop="total_cost" label="总成本" width="170" align="right" sortable>
                            <template #default="{ row }">
                                <span class="cost-main">{{ formatNumber(row.total_cost) }}</span>
                            </template>
                        </el-table-column>
                        <el-table-column prop="percentage" label="占比" width="100" align="right" sortable>
                            <template #default="{ row }">
                                {{ formatPercentage(row.percentage) }}
                            </template>
                        </el-table-column>
                    </KTable>
                </KCard>
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
    font-size: var(--k-font-md);
    font-weight: 600;
}

:deep(.el-table) {
    font-size: 14px;
}

:deep(.el-table th) {
    font-weight: 600;
}

/* 成本单元格：主数值 + 副行（占比 / 单价） */
.cost-cell {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    line-height: 1.3;
    font-variant-numeric: tabular-nums;
}

.cost-main {
    font-weight: 600;
}

.cost-sub {
    font-size: var(--k-font-xs);
    color: var(--k-color-text-secondary);
    opacity: 0.8;
}
</style>
