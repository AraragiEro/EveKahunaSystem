<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { http } from '@/http'
import { ElMessage } from 'element-plus'
import { DocumentCopy, Check } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'

const props = withDefaults(defineProps<{
    materialData?: any[]
    selectedPlan?: string | null
}>(), {
    materialData: () => [],
    selectedPlan: null
})

// localStorage key 前缀
const STORAGE_KEY_PREFIX = 'compressed_asteroid_'

// 响应式数据变量
const loading = ref(false)
const refinementRate = ref(90.6) // 化矿率，默认90.6%（百分比）
const wastePenalty = ref(0.1) // 多余矿物权重，默认0.1
const purchaseMode = ref<'扫单' | '收单'>('扫单') // 采购模式：扫单或收单
const quantityMode = ref<'缺失' | '全部'>('缺失') // 数量模式：缺失或全部
const lastFetchTime = ref<string | null>(null) // 上次获取数据的时间（ISO 格式）
const compressedAsteroidData = ref<{
    purcheses_res?: Record<string, {
        quantity: number
        total_price: number
        name: string
        name_zh: string
        avrprice: number
        volume: number
    }>
    excess_minerals_res?: Record<string, {
        quantity: number
        name: string
        name_zh: string
        price: number
    }>
    mineral_yields?: Record<string, Record<string, [number, number]>>
    total_cost?: number
    total_excess_price?: number
    is_empty?: boolean  // 标识为空数据（无缺失矿物）
} | null>(null)

// 保存数据到本地存储
const saveToLocalStorage = () => {
    if (!props.selectedPlan) {
        return
    }
    try {
        const key = `${STORAGE_KEY_PREFIX}${props.selectedPlan}`
        // 读取现有数据
        const existingDataStr = localStorage.getItem(key)
        let existingData: any = {}
        if (existingDataStr) {
            try {
                existingData = JSON.parse(existingDataStr)
            } catch (e) {
                // 如果解析失败，使用空对象
                existingData = {}
            }
        }
        
        // 根据当前模式保存数据
        const modeKey = quantityMode.value === '缺失' ? 'missing' : 'all'
        const dataToSave = {
            compressedAsteroidData: compressedAsteroidData.value,
            refinementRate: refinementRate.value,
            wastePenalty: wastePenalty.value,
            purchaseMode: purchaseMode.value,
            fetchTime: new Date().toISOString()
        }
        
        // 合并到现有数据中
        existingData[modeKey] = dataToSave
        existingData.quantityMode = quantityMode.value
        
        localStorage.setItem(key, JSON.stringify(existingData))
        lastFetchTime.value = dataToSave.fetchTime
        console.log(`压缩矿数据已保存到本地: ${props.selectedPlan} (模式: ${quantityMode.value})`)
    } catch (error) {
        console.error('保存到本地失败:', error)
    }
}

// 从本地存储加载数据
const loadFromLocalStorage = () => {
    if (!props.selectedPlan) {
        return
    }
    try {
        const key = `${STORAGE_KEY_PREFIX}${props.selectedPlan}`
        const data = localStorage.getItem(key)
        if (data) {
            const parsed = JSON.parse(data)
            
            // 恢复数量模式
            if (parsed.quantityMode !== undefined) {
                quantityMode.value = parsed.quantityMode
            }
            
            // 根据当前模式加载对应的数据
            const modeKey = quantityMode.value === '缺失' ? 'missing' : 'all'
            const modeData = parsed[modeKey]
            
            if (modeData) {
                if (modeData.compressedAsteroidData) {
                    compressedAsteroidData.value = modeData.compressedAsteroidData
                }
                if (modeData.refinementRate !== undefined) {
                    refinementRate.value = modeData.refinementRate
                }
                if (modeData.wastePenalty !== undefined) {
                    wastePenalty.value = modeData.wastePenalty
                }
                if (modeData.purchaseMode !== undefined) {
                    purchaseMode.value = modeData.purchaseMode
                }
                if (modeData.fetchTime) {
                    lastFetchTime.value = modeData.fetchTime
                }
                console.log(`从本地加载压缩矿数据: ${props.selectedPlan} (模式: ${quantityMode.value})`)
            } else {
                // 兼容旧格式：如果没有新模式数据，尝试加载旧格式
                if (parsed.compressedAsteroidData) {
                    compressedAsteroidData.value = parsed.compressedAsteroidData
                }
                if (parsed.refinementRate !== undefined) {
                    refinementRate.value = parsed.refinementRate
                }
                if (parsed.wastePenalty !== undefined) {
                    wastePenalty.value = parsed.wastePenalty
                }
                if (parsed.purchaseMode !== undefined) {
                    purchaseMode.value = parsed.purchaseMode
                }
                if (parsed.fetchTime) {
                    lastFetchTime.value = parsed.fetchTime
                }
                console.log(`从本地加载压缩矿数据(旧格式): ${props.selectedPlan}`)
            }
        }
    } catch (error) {
        console.error('从本地读取失败:', error)
    }
}

const getCompressedAsteroidData = async () => {
    // materialData 的结构是 [{ layer_id: "矿石", children: [...] }, ...]
    // 需要找到 layer_id === '矿石' 或 '冰矿产物' 的对象，然后合并它们的 children
    const mineralLayers = (props.materialData || []).filter(item => ['矿石', '冰矿产物'].includes(item.layer_id))
    // 合并所有匹配层的 children
    const allChildren: any[] = []
    mineralLayers.forEach(layer => {
        if (layer?.children && Array.isArray(layer.children)) {
            allChildren.push(...layer.children)
        }
    })
    const mineralData = allChildren.map((child: any) => ({
        type_id: child.type_id,
        type_name: child.type_name,
        quantity: child.quantity,
        real_quantity: child.real_quantity
    }))
    
    if (mineralData.length === 0) {
        ElMessage.warning('没有找到矿物数据')
        return
    }
    
    loading.value = true
    try {
        const res = await http.post('/EVE/industry/getCompressedAsteroidData', {
            mineral_data: mineralData,
            refinement_rate: refinementRate.value / 100, // 将百分比转换为小数
            waste_penalty: wastePenalty.value,
            purchase_mode: purchaseMode.value,
            quantity_mode: quantityMode.value
        })
        
        if (!res.ok) {
            ElMessage.error(`请求失败: HTTP ${res.status}`)
            ElMessage.error((await res.json()).message)
            return
        }
        
        const data = await res.json()
        
        if (data.status !== 200) {
            ElMessage.error(data.message || "获取压缩矿数据失败")
            return
        }
        
        compressedAsteroidData.value = data.data || null
        // 保存数据到本地存储
        saveToLocalStorage()
        // 根据是否为空数据显示不同的消息
        if (compressedAsteroidData.value?.is_empty) {
            ElMessage.success('无缺失矿物')
        } else {
            ElMessage.success('获取压缩矿数据成功')
        }
    } catch (error) {
        console.error('获取压缩矿数据失败:', error)
        ElMessage.error('获取压缩矿数据失败，请重试')
    } finally {
        loading.value = false
    }
}

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
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
    })
}

// 步骤2：数据转换和计算函数

// 需求矿物数据（从 props.materialData 提取）
const requiredMinerals = computed(() => {
    // 找到所有 layer_id === '矿石' 或 '冰矿产物' 的对象
    const mineralLayers = (props.materialData || []).filter(item => ['矿石', '冰矿产物'].includes(item.layer_id))
    if (mineralLayers.length === 0) {
        return []
    }
    
    // 按 type_id 分组并合并数量，统一 type_id 为字符串类型
    const mineralMap = new Map<string, {
        type_id: string
        type_name: string
        type_name_zh: string
        quantity: number
    }>()
    
    // 遍历所有匹配的层，合并它们的 children
    mineralLayers.forEach(layer => {
        if (!layer?.children || !Array.isArray(layer.children)) {
            return
        }
        
        layer.children.forEach((child: any) => {
            // 统一 type_id 为字符串类型
            const typeId = String(child.type_id || '')
            if (!typeId) return
            
            // 根据数量模式选择使用 quantity 或 real_quantity
            const quantity = quantityMode.value === '缺失' 
                ? (child.real_quantity || 0) 
                : (child.quantity || 0)
            
            if (mineralMap.has(typeId)) {
                // 如果已存在，累加数量
                const existing = mineralMap.get(typeId)!
                existing.quantity += quantity
            } else {
                // 如果不存在，创建新项
                mineralMap.set(typeId, {
                    type_id: typeId,
                    type_name: child.type_name || '',
                    type_name_zh: child.type_name_zh || child.tpye_name_zh || '',
                    quantity: quantity
                })
            }
        })
    })
    
    return Array.from(mineralMap.values())
})

// 产出矿物汇总（从 mineral_yields 按矿物ID汇总）
const producedMinerals = computed(() => {
    if (!compressedAsteroidData.value?.mineral_yields) {
        return {}
    }
    
    const summary: Record<string, {
        type_id: string
        quantity: number
    }> = {}
    
    // 遍历所有矿石的矿物产出
    Object.entries(compressedAsteroidData.value.mineral_yields).forEach(([oreId, minerals]) => {
        Object.entries(minerals).forEach(([mineralId, [yieldQuantity]]) => {
            if (!summary[mineralId]) {
                summary[mineralId] = {
                    type_id: mineralId,
                    quantity: 0
                }
            }
            summary[mineralId].quantity += yieldQuantity
        })
    })
    
    return summary
})

// 多余矿物数据
const excessMinerals = computed(() => {
    return compressedAsteroidData.value?.excess_minerals_res || {}
})

// 矿石采购表数据（将 purcheses_res 转为数组）
const orePurchaseTableData = computed(() => {
    if (!compressedAsteroidData.value?.purcheses_res) {
        return []
    }
    
    return Object.entries(compressedAsteroidData.value.purcheses_res).map(([oreId, data]) => ({
        type_id: oreId,
        name: data.name,
        name_zh: data.name_zh,
        quantity: data.quantity,
        avrprice: data.avrprice,
        total_price: data.total_price
    }))
})

// 总价计算（所有矿石的总价之和）
const totalCost = computed(() => {
    if (!compressedAsteroidData.value?.purcheses_res) {
        return 0
    }
    return Object.values(compressedAsteroidData.value.purcheses_res).reduce((sum, ore) => {
        return sum + (ore.total_price || 0)
    }, 0)
})

// 产出价值总和
const totalProducedValue = computed(() => {
    return mineralComparisonTableData.value.reduce((sum, row) => {
        return sum + (row.produced_value || 0)
    }, 0)
})

// 多余价值总和
const totalExcessValue = computed(() => {
    return mineralComparisonTableData.value.reduce((sum, row) => {
        return sum + (row.excess_value || 0)
    }, 0)
})

// 矿石采购总体积
const totalVolume = computed(() => {
    if (!compressedAsteroidData.value?.purcheses_res) {
        return 0
    }
    return Object.values(compressedAsteroidData.value.purcheses_res).reduce((sum, ore) => {
        const volume = ore.volume || 0
        const quantity = ore.quantity || 0
        return sum + (volume * quantity)
    }, 0)
})

// 预估运费（按照 20000m³ = 10000000 ISK 计算）
const estimatedShippingCost = computed(() => {
    if (totalVolume.value === 0) {
        return 0
    }
    return (totalVolume.value / 20000) * 10000000
})

// 多余价值占产出价值百分比
const excessValuePercentage = computed(() => {
    if (totalProducedValue.value === 0) {
        return 0
    }
    return (totalExcessValue.value / totalProducedValue.value) * 100
})

// 矿物对比表数据（合并需求、产出、多余矿物）
const mineralComparisonTableData = computed(() => {
    const result: Array<{
        type_id: string
        type_name: string
        type_name_zh: string
        required_quantity: number
        produced_quantity: number
        excess_quantity: number
        produced_value: number
        excess_value: number
    }> = []
    
    // 获取所有唯一的矿物ID，统一转换为字符串类型
    const mineralIds = new Set<string>()
    
    // 从需求矿物中添加
    requiredMinerals.value.forEach((mineral: any) => {
        mineralIds.add(String(mineral.type_id || ''))
    })
    
    // 从产出矿物中添加
    Object.keys(producedMinerals.value).forEach(mineralId => {
        mineralIds.add(String(mineralId))
    })
    
    // 从多余矿物中添加
    Object.keys(excessMinerals.value).forEach(mineralId => {
        mineralIds.add(String(mineralId))
    })
    
    // 构建表格数据
    mineralIds.forEach(mineralId => {
        // 统一使用字符串类型的 mineralId 进行查找
        const required = requiredMinerals.value.find((m: any) => String(m.type_id || '') === mineralId)
        const produced = producedMinerals.value[mineralId]
        const excess = excessMinerals.value[mineralId]
        
        // 获取矿物价格（从 excess_minerals_res 中获取，如果不存在则使用 0）
        const mineralPrice = excess?.price || compressedAsteroidData.value?.excess_minerals_res?.[mineralId]?.price || 0
        
        const producedQuantity = produced?.quantity || 0
        const excessQuantity = excess?.quantity || 0
        
        result.push({
            type_id: mineralId,
            type_name: required?.type_name || produced?.type_id || excess?.name || '',
            type_name_zh: required?.type_name_zh || excess?.name_zh || '',
            required_quantity: required?.quantity || 0,
            produced_quantity: producedQuantity,
            excess_quantity: excessQuantity,
            produced_value: producedQuantity * mineralPrice,
            excess_value: excessQuantity * mineralPrice
        })
    })
    
    // 过滤掉需求为0的行
    return result.filter(row => row.required_quantity > 0)
})

// 步骤5：桑吉图数据准备
const sankeyData = computed(() => {
    if (!compressedAsteroidData.value?.mineral_yields || !compressedAsteroidData.value?.purcheses_res) {
        return { nodes: [], links: [] }
    }
    
    const nodes: Array<{ name: string }> = []
    const links: Array<{ source: string; target: string; value: number }> = []
    
    // 创建节点映射，避免重复
    const nodeMap = new Map<string, number>()
    let nodeIndex = 0
    
    // 添加矿石节点（左侧）
    Object.entries(compressedAsteroidData.value.purcheses_res).forEach(([oreId, oreData]) => {
        const nodeName = oreData.name_zh || oreData.name || oreId
        if (!nodeMap.has(nodeName)) {
            nodes.push({ name: nodeName })
            nodeMap.set(nodeName, nodeIndex++)
        }
    })
    
    // 添加矿物节点（右侧）并构建连接
    Object.entries(compressedAsteroidData.value.mineral_yields).forEach(([oreId, minerals]) => {
        const oreData = compressedAsteroidData.value?.purcheses_res?.[oreId]
        if (!oreData) return
        
        const sourceName = oreData.name_zh || oreData.name || oreId
        
        Object.entries(minerals).forEach(([mineralId, [yieldQuantity]]) => {
            // 获取矿物名称
            const excessData = compressedAsteroidData.value?.excess_minerals_res?.[mineralId]
            const requiredData = requiredMinerals.value.find((m: any) => m.type_id === mineralId)
            const targetName = excessData?.name_zh || requiredData?.type_name_zh || requiredData?.type_name || mineralId
            
            // 添加矿物节点（如果不存在）
            if (!nodeMap.has(targetName)) {
                nodes.push({ name: targetName })
                nodeMap.set(targetName, nodeIndex++)
            }
            
            // 添加连接
            links.push({
                source: sourceName,
                target: targetName,
                value: yieldQuantity
            })
        })
    })
    
    return { nodes, links }
})

// 步骤6：桑吉图实现
const sankeyChartRef = ref<HTMLElement>()
let sankeyChartInstance: echarts.ECharts | null = null

// 防抖定时器
let resizeTimer: number | null = null

// 窗口resize处理函数（带防抖）
const handleResize = () => {
    if (resizeTimer) {
        clearTimeout(resizeTimer)
    }
    resizeTimer = window.setTimeout(() => {
        if (sankeyChartInstance) {
            try {
                sankeyChartInstance.resize()
            } catch (error) {
                console.error('图表resize失败:', error)
            }
        }
    }, 100)
}

// 检查容器是否准备好
const isContainerReady = (): boolean => {
    if (!sankeyChartRef.value) {
        return false
    }
    const rect = sankeyChartRef.value.getBoundingClientRect()
    return rect.width > 0 && rect.height > 0
}

// 初始化桑吉图
const initSankeyChart = () => {
    // 检查 DOM 元素是否存在
    if (!sankeyChartRef.value) {
        return
    }
    
    // 检查数据是否存在
    if (!compressedAsteroidData.value) {
        return
    }
    
    // 如果图表实例已存在，先销毁
    if (sankeyChartInstance) {
        try {
            sankeyChartInstance.dispose()
        } catch (error) {
            console.error('销毁图表实例失败:', error)
        }
        sankeyChartInstance = null
    }
    
    // 初始化图表的辅助函数（带重试限制）
    let retryCount = 0
    const maxRetries = 10
    const doInit = () => {
        if (!sankeyChartRef.value || !compressedAsteroidData.value) {
            return
        }
        
        // 如果容器尺寸为0，延迟初始化（最多重试10次）
        if (!isContainerReady()) {
            if (retryCount < maxRetries) {
                retryCount++
                setTimeout(doInit, 100)
            } else {
                console.warn('图表容器尺寸检查失败，已达到最大重试次数')
            }
            return
        }
        
        retryCount = 0 // 重置重试计数
        
        try {
            sankeyChartInstance = echarts.init(sankeyChartRef.value)
            updateSankeyChart()
        } catch (error) {
            console.error('初始化图表失败:', error)
        }
    }
    
    // 使用 nextTick + requestAnimationFrame 确保 DOM 完全准备好
    nextTick(() => {
        requestAnimationFrame(doInit)
    })
}

// 更新桑吉图
const updateSankeyChart = () => {
    // 如果图表实例不存在，先初始化
    if (!sankeyChartInstance) {
        if (compressedAsteroidData.value && sankeyChartRef.value) {
            initSankeyChart()
        }
        return
    }
    
    // 检查数据是否存在
    if (!compressedAsteroidData.value) {
        return
    }
    
    const { nodes, links } = sankeyData.value
    
    if (nodes.length === 0 || links.length === 0) {
        return
    }
    
    try {
        const option: EChartsOption = {
            tooltip: {
                trigger: 'item',
                triggerOn: 'mousemove',
                formatter: (params: any) => {
                    if (params.dataType === 'edge') {
                        return `${params.data.source} → ${params.data.target}<br/>数量: ${formatAccounting(params.data.value)}`
                    }
                    return params.name
                }
            },
            series: [
                {
                    type: 'sankey',
                    emphasis: {
                        focus: 'adjacency'
                    },
                    data: nodes,
                    links: links,
                    label: {
                        fontSize: 12
                    },
                    lineStyle: {
                        color: 'gradient',
                        curveness: 0.5
                    }
                } as any
            ]
        }
        
        sankeyChartInstance.setOption(option, true) // 使用 notMerge=true 确保完全替换
    } catch (error) {
        console.error('更新图表失败:', error)
    }
}

// 监听数据变化，更新图表
watch(
    () => sankeyData.value,
    () => {
        nextTick(() => {
            updateSankeyChart()
        })
    },
    { deep: true }
)

// 监听 compressedAsteroidData 变化，确保数据加载后初始化图表
watch(
    () => compressedAsteroidData.value,
    (newData) => {
        if (newData && sankeyChartRef.value && !sankeyChartInstance) {
            // 数据存在但图表未初始化，延迟初始化确保 DOM 准备好
            nextTick(() => {
                requestAnimationFrame(() => {
                    if (compressedAsteroidData.value && sankeyChartRef.value && !sankeyChartInstance) {
                        initSankeyChart()
                    }
                })
            })
        }
    }
)

// 监听数量模式变化，切换模式时加载对应缓存或清空数据
watch(
    () => quantityMode.value,
    () => {
        if (!props.selectedPlan) {
            return
        }
        
        // 先销毁图表实例
        if (sankeyChartInstance) {
            try {
                sankeyChartInstance.dispose()
            } catch (error) {
                console.error('销毁图表实例失败:', error)
            }
            sankeyChartInstance = null
        }
        
        // 尝试加载对应模式的数据
        try {
            const key = `${STORAGE_KEY_PREFIX}${props.selectedPlan}`
            const data = localStorage.getItem(key)
            if (data) {
                const parsed = JSON.parse(data)
                const modeKey = quantityMode.value === '缺失' ? 'missing' : 'all'
                const modeData = parsed[modeKey]
                
                if (modeData) {
                    // 有缓存数据，加载它
                    if (modeData.compressedAsteroidData) {
                        compressedAsteroidData.value = modeData.compressedAsteroidData
                    }
                    if (modeData.fetchTime) {
                        lastFetchTime.value = modeData.fetchTime
                    }
                    console.log(`切换模式，加载缓存数据: ${quantityMode.value}`)
                    
                    // 重新初始化图表
                    nextTick(() => {
                        requestAnimationFrame(() => {
                            if (compressedAsteroidData.value && sankeyChartRef.value) {
                                initSankeyChart()
                            }
                        })
                    })
                } else {
                    // 没有对应模式的缓存，清空数据
                    compressedAsteroidData.value = null
                    lastFetchTime.value = null
                    console.log(`切换模式，无缓存数据: ${quantityMode.value}`)
                }
            } else {
                // 没有本地数据，清空
                compressedAsteroidData.value = null
                lastFetchTime.value = null
            }
        } catch (error) {
            console.error('切换模式时读取缓存失败:', error)
            compressedAsteroidData.value = null
            lastFetchTime.value = null
        }
    }
)

// 监听 selectedPlan 变化，切换计划时重新加载数据
watch(
    () => props.selectedPlan,
    (newPlan) => {
        // 先销毁图表实例
        if (sankeyChartInstance) {
            try {
                sankeyChartInstance.dispose()
            } catch (error) {
                console.error('销毁图表实例失败:', error)
            }
            sankeyChartInstance = null
        }
        
        // 清除当前数据
        compressedAsteroidData.value = null
        lastFetchTime.value = null
        
        // 加载新计划的数据
        if (newPlan) {
            loadFromLocalStorage()
            // 使用 nextTick + requestAnimationFrame 确保图表容器准备好后再初始化
            nextTick(() => {
                requestAnimationFrame(() => {
                    if (compressedAsteroidData.value && sankeyChartRef.value) {
                        initSankeyChart()
                    }
                })
            })
        }
    }
)

onMounted(() => {
    // 加载本地数据
    loadFromLocalStorage()
    
    // 监听窗口大小变化
    window.addEventListener('resize', handleResize)
    
    // 数据加载后，watch 会自动触发图表初始化
    // 这里只需要确保在 DOM 准备好后，如果数据已存在，则初始化图表
    nextTick(() => {
        if (compressedAsteroidData.value && sankeyChartRef.value && !sankeyChartInstance) {
            initSankeyChart()
        }
    })
})

onUnmounted(() => {
    // 清理防抖定时器
    if (resizeTimer) {
        clearTimeout(resizeTimer)
        resizeTimer = null
    }
    
    // 销毁图表实例
    if (sankeyChartInstance) {
        try {
            sankeyChartInstance.dispose()
        } catch (error) {
            console.error('销毁图表实例失败:', error)
        }
        sankeyChartInstance = null
    }
    
    // 移除事件监听器
    window.removeEventListener('resize', handleResize)
})

// 复制矿石名称和数量
const copyOreData = () => {
    if (!orePurchaseTableData.value || orePurchaseTableData.value.length === 0) {
        ElMessage.warning('没有可复制的数据')
        return
    }
    
    // 格式化数据：每行格式为 "矿石名称 数量"
    const text = orePurchaseTableData.value.map(row => {
        const name = row.name_zh || row.name || ''
        const quantity = formatAccounting(row.quantity)
        return `${name}\t${quantity}`
    }).join('\n')
    
    // 复制到剪贴板
    navigator.clipboard.writeText(text).then(() => {
        ElMessage.success('已复制矿石名称和数量到剪贴板')
    }).catch(err => {
        console.error('复制失败:', err)
        ElMessage.error('复制失败，请重试')
    })
}

</script>

<template>
    <div>
        <div class="control-row">
            <div class="control-item">
                <label>化矿率：</label>
                <el-input-number
                    v-model="refinementRate"
                    :min="0"
                    :max="100"
                    :step="0.1"
                    :precision="1"
                    controls-position="right"
                    style="width: 150px;"
                />
                <span class="unit">%</span>
            </div>
            <div class="control-item">
                <label>多余矿物权重：</label>
                <el-input-number
                    v-model="wastePenalty"
                    :min="0"
                    :max="1"
                    :step="0.01"
                    :precision="2"
                    controls-position="right"
                    style="width: 150px;"
                />
            </div>
            <div class="control-item">
                <label>采购模式：</label>
                <el-switch
                    v-model="purchaseMode"
                    active-value="扫单"
                    inactive-value="收单"
                    active-text="扫单"
                    inactive-text="收单"
                />
            </div>
            <div class="control-item">
                <label>数量模式：</label>
                <el-switch
                    v-model="quantityMode"
                    active-value="缺失"
                    inactive-value="全部"
                    active-text="缺失"
                    inactive-text="全部"
                />
            </div>
            <el-button @click="getCompressedAsteroidData" :loading="loading">
                获取压缩矿
            </el-button>
            <div v-if="lastFetchTime" class="control-item">
                <label>上次获取时间：</label>
                <span class="fetch-time">{{ lastFetchTime }}</span>
            </div>
        </div>
        
        <!-- 矿物需求表格（未获取数据时显示） -->
        <div v-if="!compressedAsteroidData && requiredMinerals.length > 0" class="required-minerals-container">
            <el-card shadow="never">
                <template #header>
                    <span>矿物需求</span>
                </template>
                <el-table
                    :data="requiredMinerals"
                    border
                    max-height="100%"
                    show-overflow-tooltip
                    style="font-size: 14px;"
                >
                    <el-table-column label="类型" width="70">
                        <template #default="{ row }">
                            <img 
                                v-if="row?.type_id"
                                :src="`https://imageserver.eveonline.com/types/${row.type_id}/icon`" 
                                alt="类型" 
                                width="40" 
                                height="40" 
                            />
                        </template>
                    </el-table-column>
                    <el-table-column label="矿物名称" prop="type_name_zh" width="200">
                        <template #default="{ row }">
                            {{ row.type_name_zh || row.type_name }}
                        </template>
                    </el-table-column>
                    <el-table-column label="需求数量" prop="quantity" width="150">
                        <template #default="{ row }">
                            {{ formatAccounting(row.quantity) }}
                        </template>
                    </el-table-column>
                </el-table>
            </el-card>
        </div>
        
        <!-- 无缺失矿物提示 -->
        <div v-if="compressedAsteroidData?.is_empty" class="empty-minerals-container">
            <el-card shadow="hover" class="empty-minerals-card">
                <div class="empty-minerals-content">
                    <el-icon class="empty-icon" :size="64">
                        <Check />
                    </el-icon>
                    <h3 class="empty-title">无缺失矿物</h3>
                    <p class="empty-description">当前计划中所有矿物需求已满足，无需采购压缩矿石</p>
                </div>
            </el-card>
        </div>
        
        <!-- 统计卡片 -->
        <div v-if="compressedAsteroidData && !compressedAsteroidData.is_empty" class="statistics-container">
            <el-card shadow="hover" class="statistics-card">
                <el-row :gutter="20">
                    <el-col :xs="24" :sm="12" :md="8" :lg="8" :xl="8" class="statistic-col">
                        <div class="statistic-item statistic-item-volume">
                            <el-statistic 
                                :value="totalVolume" 
                                :precision="2"
                                suffix=" m³"
                            >
                                <template #title>
                                    <div class="statistic-title">
                                        <span class="statistic-icon">📦</span>
                                        矿石采购总体积
                                    </div>
                                </template>
                            </el-statistic>
                        </div>
                    </el-col>
                    <el-col :xs="24" :sm="12" :md="8" :lg="8" :xl="8" class="statistic-col">
                        <div class="statistic-item statistic-item-cost">
                            <el-statistic 
                                :value="totalCost" 
                                :precision="2"
                                suffix=" ISK"
                            >
                                <template #title>
                                    <div class="statistic-title">
                                        <span class="statistic-icon">💰</span>
                                        矿石采购总价值
                                    </div>
                                </template>
                            </el-statistic>
                        </div>
                    </el-col>
                    <el-col :xs="24" :sm="12" :md="8" :lg="8" :xl="8" class="statistic-col">
                        <div class="statistic-item statistic-item-shipping">
                            <el-statistic 
                                :value="estimatedShippingCost" 
                                :precision="2"
                                suffix=" ISK"
                            >
                                <template #title>
                                    <div class="statistic-title">
                                        <span class="statistic-icon">🚚</span>
                                        预估运费
                                    </div>
                                </template>
                            </el-statistic>
                        </div>
                    </el-col>
                    <el-col :xs="24" :sm="12" :md="12" :lg="12" :xl="12" class="statistic-col">
                        <div class="statistic-item statistic-item-produced">
                            <el-statistic 
                                :value="totalProducedValue" 
                                :precision="2"
                                suffix=" ISK"
                            >
                                <template #title>
                                    <div class="statistic-title">
                                        <span class="statistic-icon">✨</span>
                                        矿物产出总价值
                                    </div>
                                </template>
                            </el-statistic>
                        </div>
                    </el-col>
                    <el-col :xs="24" :sm="12" :md="12" :lg="12" :xl="12" class="statistic-col">
                        <div class="statistic-item statistic-item-percentage">
                            <el-statistic 
                                :value="excessValuePercentage" 
                                :precision="2"
                                suffix=" %"
                            >
                                <template #title>
                                    <div class="statistic-title">
                                        <span class="statistic-icon">📊</span>
                                        多余价值占产出价值百分比
                                    </div>
                                </template>
                            </el-statistic>
                        </div>
                    </el-col>
                </el-row>
            </el-card>
        </div>
        
        <div v-if="compressedAsteroidData && !compressedAsteroidData.is_empty" class="compressed-asteroid-container">
            <!-- 矿物对比表格 -->
            <div class="layout-item mineral-comparison">
                <el-card shadow="never">
                    <template #header>
                        <span>矿物对比</span>
                    </template>
                    <el-table
                        :data="mineralComparisonTableData"
                        border
                        max-height="100%"
                        show-overflow-tooltip
                        style="font-size: 14px;"
                    >
                        <el-table-column label="类型" width="70">
                            <template #default="{ row }">
                                <img 
                                    v-if="row?.type_id"
                                    :src="`https://imageserver.eveonline.com/types/${row.type_id}/icon`" 
                                    alt="类型" 
                                    width="40" 
                                    height="40" 
                                />
                            </template>
                        </el-table-column>
                        <el-table-column label="矿物名称" prop="type_name_zh" width="150">
                            <template #default="{ row }">
                                {{ row.type_name_zh || row.type_name }}
                            </template>
                        </el-table-column>
                        <el-table-column label="需求数量" prop="required_quantity" width="120">
                            <template #default="{ row }">
                                {{ formatAccounting(row.required_quantity) }}
                            </template>
                        </el-table-column>
                        <el-table-column label="产出数量" prop="produced_quantity" width="120">
                            <template #default="{ row }">
                                {{ formatAccounting(row.produced_quantity) }}
                            </template>
                        </el-table-column>
                        <el-table-column label="产出价值" prop="produced_value" width="150">
                            <template #header>
                                产出价值 {{ formatAccounting(totalProducedValue) }}
                            </template>
                            <template #default="{ row }">
                                {{ formatAccounting(row.produced_value) }}
                            </template>
                        </el-table-column>
                        <el-table-column label="多余价值" prop="excess_value" width="150">
                            <template #header>
                                多余价值 {{ formatAccounting(totalExcessValue) }}
                            </template>
                            <template #default="{ row }">
                                {{ formatAccounting(row.excess_value) }}
                            </template>
                        </el-table-column>
                    </el-table>
                </el-card>
            </div>
            
            <!-- 矿石采购表格 -->
            <div class="layout-item ore-purchase">
                <el-card shadow="never">
                    <template #header>
                        <span>矿石采购表</span>
                    </template>
                    <el-table
                        :data="orePurchaseTableData"
                        border
                        max-height="100%"
                        show-overflow-tooltip
                        style="font-size: 14px;"
                    >
                        <el-table-column width="70">
                            <template #header>
                                <el-button 
                                    type="primary" 
                                    size="small" 
                                    square
                                    @click="copyOreData"
                                    :icon="DocumentCopy"
                                    title="复制全部"
                                />
                            </template>
                            <template #default="{ row }">
                                <img 
                                    v-if="row?.type_id"
                                    :src="`https://imageserver.eveonline.com/types/${row.type_id}/icon`" 
                                    alt="类型" 
                                    width="40" 
                                    height="40" 
                                />
                            </template>
                        </el-table-column>
                        <el-table-column label="矿石名称" prop="name_zh" width="200">
                            <template #default="{ row }">
                                {{ row.name_zh || row.name }}
                            </template>
                        </el-table-column>
                        <el-table-column label="数量" prop="quantity" width="120">
                            <template #default="{ row }">
                                {{ formatAccounting(row.quantity) }}
                            </template>
                        </el-table-column>
                        <el-table-column label="平均价格" prop="avrprice" width="150">
                            <template #default="{ row }">
                                {{ formatAccounting(row.avrprice) }}
                            </template>
                        </el-table-column>
                        <el-table-column label="总价" prop="total_price" width="150">
                            <template #header>
                                总价 {{ formatAccounting(totalCost) }}
                            </template>
                            <template #default="{ row }">
                                {{ formatAccounting(row.total_price) }}
                            </template>
                        </el-table-column>
                    </el-table>
                </el-card>
            </div>
            
            <!-- 桑吉图 -->
            <div class="layout-item sankey-chart">
                <el-card shadow="never">
                    <template #header>
                        <span>矿石产出矿物关系图</span>
                    </template>
                    <div 
                        ref="sankeyChartRef" 
                        style="width: 100%; height: 600px;"
                    ></div>
                </el-card>
            </div>
        </div>
    </div>
</template>

<style scoped>
.control-row {
    display: flex;
    align-items: center;
    gap: 20px;
    margin-bottom: 20px;
    flex-wrap: wrap;
}

.control-item {
    display: flex;
    align-items: center;
    gap: 8px;
}

.control-item label {
    white-space: nowrap;
    font-size: 14px;
}

.control-item .unit {
    font-size: 14px;
    color: #606266;
}

.control-item .fetch-time {
    font-size: 14px;
    color: #909399;
}

.required-minerals-container {
    margin-top: 20px;
}

.empty-minerals-container {
    margin-top: 20px;
    margin-bottom: 20px;
}

.empty-minerals-card {
    border-radius: 8px;
    overflow: hidden;
}

.empty-minerals-card :deep(.el-card__body) {
    padding: 60px 40px;
}

.empty-minerals-content {
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 20px;
}

.empty-icon {
    color: var(--el-color-success);
    margin-bottom: 10px;
}

.empty-title {
    font-size: 24px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin: 0;
}

.empty-description {
    font-size: 16px;
    color: var(--el-text-color-regular);
    margin: 0;
    line-height: 1.6;
}

.statistics-container {
    margin-top: 20px;
    margin-bottom: 20px;
}

.statistics-card {
    border-radius: 8px;
    overflow: hidden;
}

.statistics-card :deep(.el-card__body) {
    padding: 24px;
}

.statistic-col {
    margin-bottom: 20px;
}

.statistic-col:last-child,
.statistic-col:nth-last-child(2) {
    margin-bottom: 0;
}

.statistic-item {
    padding: 28px 24px;
    text-align: center;
    border-radius: 8px;
    background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
    border: 1px solid var(--el-border-color-lighter);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    min-height: 140px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    position: relative;
    overflow: hidden;
    box-sizing: border-box;
}

.statistic-item::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--el-color-primary), var(--el-color-primary-light-3));
    opacity: 0;
    transition: opacity 0.3s;
}

.statistic-item:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    border-color: var(--el-color-primary-light-5);
    background: linear-gradient(135deg, #ffffff 0%, #f0f9ff 100%);
}

.statistic-item:hover::before {
    opacity: 1;
}

.statistic-item-volume {
    border-top-color: #409eff;
}

.statistic-item-cost {
    border-top-color: #67c23a;
}

.statistic-item-shipping {
    border-top-color: #e6a23c;
}

.statistic-item-produced {
    border-top-color: #909399;
}

.statistic-item-percentage {
    border-top-color: #f56c6c;
}

.statistic-title {
    font-size: 14px;
    color: var(--el-text-color-regular);
    margin-bottom: 12px;
    font-weight: 500;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    line-height: 1.5;
}

.statistic-icon {
    font-size: 18px;
    display: inline-block;
}

.statistic-item :deep(.el-statistic__head) {
    margin-bottom: 12px;
}

.statistic-item :deep(.el-statistic__number) {
    font-size: 28px;
    font-weight: 700;
    color: var(--el-color-primary);
    line-height: 1.2;
    letter-spacing: -0.5px;
}

.statistic-item :deep(.el-statistic__suffix) {
    font-size: 18px;
    color: var(--el-text-color-secondary);
    margin-left: 4px;
    font-weight: 500;
}

/* 响应式优化 */
@media (max-width: 768px) {
    .statistics-card :deep(.el-card__body) {
        padding: 16px;
    }
    
    .statistic-col {
        margin-bottom: 16px;
    }
    
    .statistic-col:last-child {
        margin-bottom: 0;
    }
    
    .statistic-item {
        padding: 20px 16px;
        min-height: 120px;
    }
    
    .statistic-item :deep(.el-statistic__number) {
        font-size: 24px;
    }
    
    .statistic-title {
        font-size: 13px;
    }
}

@media (min-width: 769px) and (max-width: 991px) {
    .statistic-col {
        margin-bottom: 16px;
    }
    
    .statistic-col:nth-child(3) {
        margin-bottom: 0;
    }
}

@media (min-width: 992px) {
    .statistic-col {
        margin-bottom: 20px;
    }
    
    .statistic-col:nth-child(3),
    .statistic-col:nth-child(4),
    .statistic-col:nth-child(5) {
        margin-bottom: 0;
    }
}

.compressed-asteroid-container {
    margin-top: 20px;
    display: flex;
    flex-direction: column;
    gap: 20px;
}

.layout-item {
    width: 100%;
}

/* 小于1800px：三个组件分三行 */
@media (max-width: 1799px) {
    .compressed-asteroid-container {
        flex-direction: column;
    }
    
    .layout-item {
        width: 100%;
    }
}

/* 大于1800px且小于等于2300px：两个表格第一行，桑基图第二行 */
@media (min-width: 1800px) and (max-width: 2300px) {
    .compressed-asteroid-container {
        display: grid;
        grid-template-columns: 1fr 1fr;
        grid-template-rows: auto auto;
        gap: 20px;
    }
    
    .mineral-comparison {
        grid-column: 1;
        grid-row: 1;
    }
    
    .ore-purchase {
        grid-column: 2;
        grid-row: 1;
    }
    
    .sankey-chart {
        grid-column: 1 / 3;
        grid-row: 2;
    }
}

/* 大于2300px：三个组件同一行，宽度可调 */
@media (min-width: 2301px) {
    .compressed-asteroid-container {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        grid-template-rows: auto;
        gap: 20px;
    }
    
    .mineral-comparison {
        grid-column: 1;
        grid-row: 1;
    }
    
    .ore-purchase {
        grid-column: 2;
        grid-row: 1;
    }
    
    .sankey-chart {
        grid-column: 3;
        grid-row: 1;
    }
}
</style>