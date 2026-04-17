<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { http } from '@/http'
import { ElMessage } from 'element-plus'
import { DocumentCopy, Check } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { getChartThemeColors, themedTooltip, onThemeTokenChange } from '@/utils/echartsTheme'

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
const shortagePenalty = ref(2.0) // 不足矿物权重，默认2.0
const liquidityImpact = ref(5.0) // 收单流动性溢价系数，默认0（不启用）
const purchaseTimeLimit = ref(7) // 采购时间上限（天），默认7天
const shippingCostPerVolume = ref(0) // 运费设置，单位为isk/立方，默认0
const purchaseMode = ref<'扫单' | '收单'>('扫单') // 采购模式：扫单或收单
const quantityMode = ref<'缺失' | '全部'>('缺失') // 数量模式：缺失或全部
const lastFetchTime = ref<string | null>(null) // 上次获取数据的时间（ISO 格式）
const useCustomData = ref(false) // 是否使用自定义数据
const customMineralData = ref<Array<{
    type_id: number
    type_name: string
    type_name_zh: string
    quantity: number
    real_quantity: number
}>>([]) // 自定义矿物数据
const importDialogVisible = ref(false) // 导入弹窗显示状态
const importText = ref('') // 导入的文本内容
const importLoading = ref(false) // 导入处理中的状态
const compressedAsteroidData = ref<{
    purcheses_res?: Record<string, {
        quantity: number
        total_price: number
        total_price_with_liquidity?: number
        name: string
        name_zh: string
        avrprice: number
        base_avrprice?: number
        liquidity_premium_rate?: number
        volume: number
    }>
    excess_minerals_res?: Record<string, {
        quantity: number
        name: string
        name_zh: string
        price: number
    }>
    shortage_minerals_res?: Record<string, {
        quantity: number
        name: string
        name_zh: string
        price: number
    }>
    mineral_yields?: Record<string, Record<string, [number, number]>>
    total_cost?: number
    total_cost_with_liquidity?: number
    total_excess_price?: number
    mineral_purchases_res?: Record<string, {
        quantity: number
        total_price: number
        name: string
        name_zh: string
        avrprice: number
        volume: number
    }>
    total_mineral_cost?: number
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
            shortagePenalty: shortagePenalty.value,
            purchaseMode: purchaseMode.value,
            liquidityImpact: liquidityImpact.value,
            purchaseTimeLimit: purchaseTimeLimit.value,
            shippingCostPerVolume: shippingCostPerVolume.value,
            fetchTime: new Date().toISOString()
        }
        
        // 合并到现有数据中
        existingData[modeKey] = dataToSave
        existingData.quantityMode = quantityMode.value
        existingData.useCustomData = useCustomData.value
        existingData.customMineralData = customMineralData.value
        
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
            
            // 恢复自定义数据相关设置
            if (parsed.useCustomData !== undefined) {
                useCustomData.value = parsed.useCustomData
            }
            if (parsed.customMineralData !== undefined && Array.isArray(parsed.customMineralData)) {
                customMineralData.value = parsed.customMineralData
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
                if (modeData.shortagePenalty !== undefined) {
                    shortagePenalty.value = modeData.shortagePenalty
                }
                if (modeData.purchaseMode !== undefined) {
                    purchaseMode.value = modeData.purchaseMode
                }
                if (modeData.liquidityImpact !== undefined) {
                    liquidityImpact.value = modeData.liquidityImpact
                }
                if (modeData.purchaseTimeLimit !== undefined) {
                    purchaseTimeLimit.value = modeData.purchaseTimeLimit
                }
                if (modeData.shippingCostPerVolume !== undefined) {
                    shippingCostPerVolume.value = modeData.shippingCostPerVolume
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
    let mineralData: any[] = []
    
    // 如果使用自定义数据，使用自定义数据
    if (useCustomData.value && customMineralData.value.length > 0) {
        mineralData = customMineralData.value.map((item) => ({
            type_id: item.type_id,
            type_name: item.type_name,
            quantity: item.quantity,
            real_quantity: item.real_quantity
        }))
    } else {
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
        mineralData = allChildren.map((child: any) => ({
            type_id: child.type_id,
            type_name: child.type_name,
            quantity: child.quantity,
            real_quantity: child.real_quantity
        }))
    }
    
    if (mineralData.length === 0) {
        ElMessage.warning('没有找到矿物数据')
        return
    }
    
    loading.value = true
    try {
        // 自定义数据模式下，quantity_mode 参数应该被忽略（因为 quantity 和 real_quantity 相同）
        const quantityModeParam = useCustomData.value ? '全部' : quantityMode.value
        // 仅在收单模式下启用流动性溢价参数，其余情况下传 0
        const liquidityImpactParam = purchaseMode.value === '收单' ? liquidityImpact.value : 0.0
        // 仅在收单模式下传递采购时间上限参数
        const purchaseTimeLimitParam = purchaseMode.value === '收单' ? purchaseTimeLimit.value : 7
        const res = await http.post('/EVE/industry/getCompressedAsteroidData', {
            mineral_data: mineralData,
            refinement_rate: refinementRate.value / 100, // 将百分比转换为小数
            waste_penalty: wastePenalty.value,
            shortage_penalty: shortagePenalty.value,
            purchase_mode: purchaseMode.value,
            quantity_mode: quantityModeParam,
            liquidity_impact: liquidityImpactParam,
            purchase_time_limit: purchaseTimeLimitParam,
            shipping_cost_per_volume: shippingCostPerVolume.value
        })
        
        if (!res.ok) {
            try {
                const errorData = await res.json()
                ElMessage.error(errorData.message || `请求失败: HTTP ${res.status}`)
            } catch {
                ElMessage.error(`请求失败: HTTP ${res.status}`)
            }
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
    // 如果使用自定义数据，直接返回自定义数据
    if (useCustomData.value && customMineralData.value.length > 0) {
        return customMineralData.value
    }
    
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

// 不足矿物数据
const shortageMinerals = computed(() => {
    return compressedAsteroidData.value?.shortage_minerals_res || {}
})

// 矿石采购表数据（将 purcheses_res 转为数组）
const orePurchaseTableData = computed(() => {
    if (!compressedAsteroidData.value?.purcheses_res) {
        return []
    }
    
    return Object.entries(compressedAsteroidData.value.purcheses_res).map(([oreId, data]) => {
        const basePrice = data.base_avrprice ?? data.avrprice
        
        // 计算产出价值：从 mineral_yields 中获取该矿石产出的所有矿物，计算总价值
        let outputValue = 0
        if (compressedAsteroidData.value?.mineral_yields?.[oreId]) {
            Object.entries(compressedAsteroidData.value.mineral_yields[oreId]).forEach(([mineralId, [yieldQuantity]]) => {
                // 获取矿物的jitabuy价格（优先从 shortage_minerals_res 获取，然后从 excess_minerals_res 获取）
                const mineralPrice = 
                    compressedAsteroidData.value?.shortage_minerals_res?.[mineralId]?.price ||
                    compressedAsteroidData.value?.excess_minerals_res?.[mineralId]?.price ||
                    0
                outputValue += yieldQuantity * mineralPrice
            })
        }
        
        return {
            type_id: oreId,
            name: data.name,
            name_zh: data.name_zh,
            quantity: data.quantity,
            // 表格主展示使用基准均价
            avrprice: basePrice,
            // 保留基准价字段以便需要时调试
            base_avrprice: basePrice,
            liquidity_premium_rate: data.liquidity_premium_rate,
            // 表格主展示使用基准总价
            total_price: data.total_price,
            total_price_with_liquidity: data.total_price_with_liquidity,
            // 产出价值（精炼后的价值，使用jitabuy价格）
            output_value: outputValue
        }
    })
})

// 总价计算（所有矿石的总价之和，使用基准成本）
const totalCost = computed(() => {
    // 优先使用后端返回的基准总成本
    if (compressedAsteroidData.value?.total_cost !== undefined) {
        return compressedAsteroidData.value.total_cost
    }
    // 兼容旧数据：从表数据汇总
    if (!compressedAsteroidData.value?.purcheses_res) {
        return 0
    }
    return Object.values(compressedAsteroidData.value.purcheses_res).reduce((sum, ore) => {
        return sum + (ore.total_price || 0)
    }, 0)
})

// 矿物采购表数据（将 mineral_purchases_res 转为数组）
const mineralPurchaseTableData = computed(() => {
    if (!compressedAsteroidData.value?.mineral_purchases_res) {
        return []
    }
    
    return Object.entries(compressedAsteroidData.value.mineral_purchases_res).map(([mineralId, data]) => ({
        type_id: mineralId,
        name: data.name,
        name_zh: data.name_zh,
        quantity: data.quantity,
        avrprice: data.avrprice,
        total_price: data.total_price
    }))
})

// 矿物采购总价值
const totalMineralCost = computed(() => {
    // 优先使用后端返回的值
    if (compressedAsteroidData.value?.total_mineral_cost !== undefined) {
        return compressedAsteroidData.value.total_mineral_cost
    }
    // 如果后端未返回，则从前端数据计算
    if (!compressedAsteroidData.value?.mineral_purchases_res) {
        return 0
    }
    return Object.values(compressedAsteroidData.value.mineral_purchases_res).reduce((sum, mineral) => {
        return sum + (mineral.total_price || 0)
    }, 0)
})

// 总采购价值（矿石采购总价值 + 矿物采购总价值）
const totalPurchaseCost = computed(() => {
    return totalCost.value + totalMineralCost.value
})

// 产出价值总和
const totalProducedValue = computed(() => {
    return mineralComparisonTableData.value.reduce((sum, row) => {
        return sum + (row.produced_value || 0)
    }, 0)
})

// 折扣比例（矿物产出总价值 / 矿石采购总价值）
const discountRatio = computed(() => {
    if (totalCost.value === 0) {
        return 0
    }
    return (totalCost.value / totalProducedValue.value) * 100
})

// 多余价值总和
const totalExcessValue = computed(() => {
    return mineralComparisonTableData.value.reduce((sum, row) => {
        return sum + (row.excess_value || 0)
    }, 0)
})

// 不足价值总和
const totalShortageValue = computed(() => {
    return mineralComparisonTableData.value.reduce((sum, row) => {
        return sum + (row.shortage_value || 0)
    }, 0)
})

// 需求总价值（所有需求矿物的总价值）
const totalRequiredValue = computed(() => {
    if (!requiredMinerals.value || requiredMinerals.value.length === 0) {
        return 0
    }
    
    return requiredMinerals.value.reduce((sum, mineral: any) => {
        const mineralId = String(mineral.type_id || '')
        const quantity = mineral.quantity || 0
        
        // 只计算正数需求，负数表示有盈余，不需要计入需求总价值
        if (quantity <= 0) {
            console.log(`矿物 ${mineralId} 需求为 ${quantity}，不需要计入需求总价值`)
            return sum
        }
        
        // 从 excess_minerals_res 或 shortage_minerals_res 中获取价格
        const price = compressedAsteroidData.value?.excess_minerals_res?.[mineralId]?.price 
            || compressedAsteroidData.value?.shortage_minerals_res?.[mineralId]?.price 
            || 0
        
        console.log(`矿物 ${mineralId} 需求为 ${quantity}，价格为 ${price}，需要计入需求总价值`)
        console.log(`需求总价值为 ${sum + (quantity * price)}`)
        return sum + (quantity * price)
    }, 0)
})

// 矿石采购总体积
const totalOreVolume = computed(() => {
    if (!compressedAsteroidData.value?.purcheses_res) {
        return 0
    }
    return Object.values(compressedAsteroidData.value.purcheses_res).reduce((sum, ore) => {
        const volume = ore.volume || 0
        const quantity = ore.quantity || 0
        return sum + (volume * quantity)
    }, 0)
})

// 矿物采购总体积
const totalMineralVolume = computed(() => {
    if (!compressedAsteroidData.value?.mineral_purchases_res) {
        return 0
    }
    return Object.values(compressedAsteroidData.value.mineral_purchases_res).reduce((sum, mineral) => {
        const volume = mineral.volume || 0
        const quantity = mineral.quantity || 0
        return sum + (volume * quantity)
    }, 0)
})

// 采购总体积（矿石 + 矿物）
const totalVolume = computed(() => {
    return totalOreVolume.value + totalMineralVolume.value
})

// 预估运费（使用用户设置的运费单价）
const estimatedShippingCost = computed(() => {
    if (totalVolume.value === 0 || shippingCostPerVolume.value === 0) {
        return 0
    }
    return totalVolume.value * shippingCostPerVolume.value
})

// 总成本（采购价值 + 运费）
const totalCostWithShipping = computed(() => {
    return totalPurchaseCost.value + estimatedShippingCost.value
})

// 总成本折扣比例（总成本 / 需求总价值 * 100）
const totalCostDiscountRatio = computed(() => {
    if (totalRequiredValue.value === 0) {
        return 0
    }
    return (totalCostWithShipping.value / totalRequiredValue.value) * 100
})

// 多余价值占产出价值百分比
const excessValuePercentage = computed(() => {
    if (totalProducedValue.value === 0) {
        return 0
    }
    return (totalExcessValue.value / totalProducedValue.value) * 100
})

// 矿物对比表数据（合并需求、产出、多余矿物、不足矿物）
const mineralComparisonTableData = computed(() => {
    const result: Array<{
        type_id: string
        type_name: string
        type_name_zh: string
        required_quantity: number
        produced_quantity: number
        excess_quantity: number
        shortage_quantity: number
        produced_value: number
        excess_value: number
        shortage_value: number
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
    
    // 从不足矿物中添加
    Object.keys(shortageMinerals.value).forEach(mineralId => {
        mineralIds.add(String(mineralId))
    })
    
    // 构建表格数据
    mineralIds.forEach(mineralId => {
        // 统一使用字符串类型的 mineralId 进行查找
        const required = requiredMinerals.value.find((m: any) => String(m.type_id || '') === mineralId)
        const produced = producedMinerals.value[mineralId]
        const excess = excessMinerals.value[mineralId]
        const shortage = shortageMinerals.value[mineralId]
        
        // 获取矿物价格（优先从 shortage_minerals_res 获取，然后从 excess_minerals_res 获取，如果不存在则使用 0）
        const mineralPrice = shortage?.price || excess?.price || compressedAsteroidData.value?.shortage_minerals_res?.[mineralId]?.price || compressedAsteroidData.value?.excess_minerals_res?.[mineralId]?.price || 0
        
        const producedQuantity = produced?.quantity || 0
        const excessQuantity = excess?.quantity || 0
        const shortageQuantity = shortage?.quantity || 0
        
        result.push({
            type_id: mineralId,
            type_name: required?.type_name || produced?.type_id || excess?.name || shortage?.name || '',
            type_name_zh: required?.type_name_zh || excess?.name_zh || shortage?.name_zh || '',
            required_quantity: required?.quantity || 0,
            produced_quantity: producedQuantity,
            excess_quantity: excessQuantity,
            shortage_quantity: shortageQuantity,
            produced_value: producedQuantity * mineralPrice,
            excess_value: excessQuantity * mineralPrice,
            shortage_value: shortageQuantity * mineralPrice
        })
    })
    
    // 显示所有有需求或产出的矿物（过滤掉既无需求也无产出的行）
    return result.filter(row => row.required_quantity > 0 || row.produced_quantity > 0)
})

// 步骤5：桑吉图数据准备（按价值分配比例）
const sankeyData = computed(() => {
    if (!compressedAsteroidData.value?.mineral_yields || !compressedAsteroidData.value?.purcheses_res) {
        return { nodes: [], links: [] }
    }
    
    const nodes: Array<{ name: string }> = []
    const links: Array<{
        source: string
        target: string
        value: number           // 显示用的“价值占比”（百分比）
        rawValue: number        // 实际价值（ISK）
        percentage: number      // 占比（同 value，单独存一份方便 tooltip 使用）
    }> = []
    
    // 创建节点映射，避免重复
    const nodeMap = new Map<string, number>()
    let nodeIndex = 0
    
    // 记录每个矿石对应的总产出价值，用于计算占比
    const oreTotalValueMap = new Map<string, number>()
    
    // 添加矿石节点（左侧）
    Object.entries(compressedAsteroidData.value.purcheses_res).forEach(([oreId, oreData]) => {
        const nodeName = oreData.name_zh || oreData.name || oreId
        if (!nodeMap.has(nodeName)) {
            nodes.push({ name: nodeName })
            nodeMap.set(nodeName, nodeIndex++)
        }
    })
    
    // 临时保存原始价值，用于后续计算占比
    const tempLinks: Array<{
        source: string
        target: string
        rawValue: number
    }> = []
    
    // 添加矿物节点（右侧）并构建连接（使用价值而非数量）
    Object.entries(compressedAsteroidData.value.mineral_yields).forEach(([oreId, minerals]) => {
        const oreData = compressedAsteroidData.value?.purcheses_res?.[oreId]
        if (!oreData) return
        
        const sourceName = oreData.name_zh || oreData.name || oreId
        
        Object.entries(minerals).forEach(([mineralId, [yieldQuantity]]) => {
            // 获取矿物名称
            const excessData = compressedAsteroidData.value?.excess_minerals_res?.[mineralId]
            const requiredData = requiredMinerals.value.find((m: any) => m.type_id === mineralId)
            const targetName = excessData?.name_zh || requiredData?.type_name_zh || requiredData?.type_name || mineralId
            
            // 获取矿物价格（与矿物对比表中一致的价格获取逻辑）
            const shortageData = compressedAsteroidData.value?.shortage_minerals_res?.[mineralId]
            const mineralPrice =
                shortageData?.price ||
                excessData?.price ||
                compressedAsteroidData.value?.shortage_minerals_res?.[mineralId]?.price ||
                compressedAsteroidData.value?.excess_minerals_res?.[mineralId]?.price ||
                0
            
            // 按价值计算（数量 * 单价）
            const rawValue = yieldQuantity * mineralPrice
            if (!rawValue || rawValue <= 0) {
                return
            }
            
            // 添加矿物节点（如果不存在）
            if (!nodeMap.has(targetName)) {
                nodes.push({ name: targetName })
                nodeMap.set(targetName, nodeIndex++)
            }
            
            // 记录原始价值
            tempLinks.push({
                source: sourceName,
                target: targetName,
                rawValue
            })
            
            // 累计该矿石的总产出价值
            const prevTotal = oreTotalValueMap.get(sourceName) || 0
            oreTotalValueMap.set(sourceName, prevTotal + rawValue)
        })
    })
    
    // 将原始价值转换为“占比”（百分比），保证每个矿石的输出总和为 100
    tempLinks.forEach(link => {
        const oreTotal = oreTotalValueMap.get(link.source) || 0
        if (!oreTotal || oreTotal <= 0) {
            return
        }
        const percentage = (link.rawValue / oreTotal) * 100
        links.push({
            source: link.source,
            target: link.target,
            value: link.rawValue,  // 使用实际价值，让条带宽度按价值比例显示
            rawValue: link.rawValue,
            percentage  // 保留百分比用于 tooltip 显示
        })
    })
    
    return { nodes, links }
})

// 步骤6：桑吉图实现
const sankeyChartRef = ref<HTMLElement>()
let sankeyChartInstance: echarts.ECharts | null = null
let cleanupThemeWatcher: (() => void) | null = null

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
    const c = getChartThemeColors()
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
                ...themedTooltip(c),
                trigger: 'item',
                triggerOn: 'mousemove',
                formatter: (params: any) => {
                    if (params.dataType === 'edge') {
                        const rawValue = params.data.rawValue ?? params.data.value
                        const percentage = params.data.percentage ?? params.data.value
                        return `${params.data.source} → ${params.data.target}` +
                            `<br/>价值: ${formatAccounting(rawValue)} ISK` +
                            `<br/>价值占比: ${formatAccounting(percentage)}%`
                    }
                    
                    // 节点（尤其是右侧矿物节点）显示总价值
                    const name = params.name
                    // 汇总所有指向该节点的连线 rawValue 作为总价值
                    const totalValue = sankeyData.value.links
                        .filter(link => link.target === name)
                        .reduce((sum, link) => sum + (link.rawValue || 0), 0)
                    
                    if (totalValue > 0) {
                        return `${name}<br/>总价值: ${formatAccounting(totalValue)} ISK`
                    }
                    
                    return name
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
                        fontSize: 12,
                        color: c.text
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

// 监听 useCustomData 变化
watch(
    () => useCustomData.value,
    (newValue) => {
        if (newValue) {
            // 切换到自定义数据模式
            // 如果有自定义数据且已计算过，直接显示结果
            if (customMineralData.value.length > 0 && compressedAsteroidData.value) {
                console.log('切换到自定义数据模式，使用已有计算结果')
                // 数据已经存在，图表会自动更新
            } else if (customMineralData.value.length > 0) {
                // 有自定义数据但未计算，可以提示用户点击求解
                console.log('切换到自定义数据模式，请点击求解按钮进行计算')
            } else {
                console.log('切换到自定义数据模式，但暂无自定义数据')
            }
        } else {
            // 切换回普通模式
            console.log('切换回普通模式')
            // 如果当前有计算结果，可能需要重新计算（因为数据源变了）
            if (compressedAsteroidData.value) {
                // 可以选择清空数据或保持显示（这里选择保持显示，用户需要时再点击求解）
            }
        }
        // 保存状态
        saveToLocalStorage()
    }
)

onMounted(() => {
    cleanupThemeWatcher = onThemeTokenChange(() => {
        updateSankeyChart()
    })
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
    cleanupThemeWatcher?.()
    cleanupThemeWatcher = null
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

// 复制矿物名称和数量
const copyMineralData = () => {
    if (!mineralPurchaseTableData.value || mineralPurchaseTableData.value.length === 0) {
        ElMessage.warning('没有可复制的数据')
        return
    }
    
    // 格式化数据：每行格式为 "矿物名称 数量"
    const text = mineralPurchaseTableData.value.map(row => {
        const name = row.name_zh || row.name || ''
        const quantity = formatAccounting(row.quantity)
        return `${name}\t${quantity}`
    }).join('\n')
    
    // 复制到剪贴板
    navigator.clipboard.writeText(text).then(() => {
        ElMessage.success('已复制矿物名称和数量到剪贴板')
    }).catch(err => {
        console.error('复制失败:', err)
        ElMessage.error('复制失败，请重试')
    })
}

// 解析导入文本
const parseImportText = async () => {
    if (!importText.value.trim()) {
        ElMessage.warning('请输入要导入的内容')
        return
    }
    
    importLoading.value = true
    const lines = importText.value.split('\n')
    const parsedData: Array<{
        type_id: number
        type_name: string
        type_name_zh: string
        quantity: number
        real_quantity: number
    }> = []
    const errors: string[] = []
    const mineralMap = new Map<number, {
        type_id: number
        type_name: string
        type_name_zh: string
        quantity: number
    }>()
    
    try {
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim()
            if (!line) continue
            
            // 使用空格或制表符切分
            const parts = line.split(/\s+/).filter(part => part.length > 0)
            if (parts.length === 0) continue
            
            let quantity: number | null = null
            const nameParts: string[] = []
            
            // 从左到右遍历，找到第一个数字作为需求数量
            for (const part of parts) {
                // 尝试解析为数字（支持千分位分隔符）
                const numStr = part.replace(/,/g, '')
                const num = parseFloat(numStr)
                if (!isNaN(num) && isFinite(num) && num > 0) {
                    quantity = num
                    break
                } else {
                    nameParts.push(part)
                }
            }
            
            if (quantity === null) {
                errors.push(`第 ${i + 1} 行：未找到有效的数量`)
                continue
            }
            
            if (nameParts.length === 0) {
                errors.push(`第 ${i + 1} 行：未找到矿物名称`)
                continue
            }
            
            // 尝试组合名称片段查询
            let found = false
            for (let j = nameParts.length; j > 0; j--) {
                const testName = nameParts.slice(0, j).join(' ')
                try {
                    const res = await http.post('/EVE/industry/searchMineralOrIceProduct', {
                        name: testName
                    })
                    
                    if (!res.ok) {
                        // 如果有后端返回的message，记录到errors中（但不立即显示，避免循环中产生太多消息）
                        try {
                            const errorData = await res.json()
                            if (errorData.message && j === nameParts.length) {
                                // 只在最后一次尝试失败时记录，避免重复
                                errors.push(`第 ${i + 1} 行查询失败: ${errorData.message}`)
                            }
                        } catch {
                            // 无法解析响应体，继续重试
                        }
                        continue
                    }
                    
                    const data = await res.json()
                    if (data.status === 200 && data.data) {
                        const typeId = Number(data.data.type_id)
                        
                        // 如果已存在，累加数量
                        if (mineralMap.has(typeId)) {
                            const existing = mineralMap.get(typeId)!
                            existing.quantity += quantity
                        } else {
                            mineralMap.set(typeId, {
                                type_id: typeId,
                                type_name: data.data.type_name || '',
                                type_name_zh: data.data.type_name_zh || '',
                                quantity: quantity
                            })
                        }
                        found = true
                        break
                    }
                } catch (error) {
                    // 继续尝试下一个名称片段
                    continue
                }
            }
            
            if (!found) {
                errors.push(`第 ${i + 1} 行：无法识别矿物 "${nameParts.join(' ')}"`)
            }
        }
        
        // 转换为数组格式
        mineralMap.forEach((value) => {
            parsedData.push({
                type_id: value.type_id,
                type_name: value.type_name,
                type_name_zh: value.type_name_zh,
                quantity: value.quantity,
                real_quantity: value.quantity
            })
        })
        
        if (parsedData.length === 0) {
            ElMessage.error('未能解析出任何有效的矿物数据')
            return
        }
        
        // 保存解析结果
        customMineralData.value = parsedData
        saveToLocalStorage()
        
        // 显示结果
        const successMsg = `成功导入 ${parsedData.length} 种矿物`
        if (errors.length > 0) {
            ElMessage.warning(`${successMsg}，但有 ${errors.length} 行解析失败`)
            console.warn('解析错误:', errors)
        } else {
            ElMessage.success(successMsg)
        }
        
        // 关闭弹窗
        importDialogVisible.value = false
        importText.value = ''
        
        // 如果已开启自定义数据模式，自动触发计算
        if (useCustomData.value && parsedData.length > 0) {
            await getCompressedAsteroidData()
        }
    } catch (error) {
        console.error('解析导入文本失败:', error)
        ElMessage.error('解析导入文本失败，请重试')
    } finally {
        importLoading.value = false
    }
}

// 打开导入弹窗
const openImportDialog = () => {
    importDialogVisible.value = true
    importText.value = ''
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
                <label>多余矿物惩罚：</label>
                <el-input-number
                    v-model="wastePenalty"
                    :min="0"
                    :max="100"
                    :step="0.1"
                    :precision="2"
                    controls-position="right"
                    style="width: 150px;"
                />
            </div>
            <!-- <div class="control-item">
                <label>不足矿物惩罚：</label>
                <el-input-number
                    v-model="shortagePenalty"
                    :min="0"
                    :max="100"
                    :step="0.1"
                    :precision="2"
                    controls-position="right"
                    style="width: 150px;"
                />
            </div> -->
            <div class="control-item">
                <label>运费设置：</label>
                <el-input-number
                    v-model="shippingCostPerVolume"
                    :min="0"
                    :step="1"
                    :precision="0"
                    controls-position="right"
                    style="width: 150px;"
                />
                <span class="unit">isk/m³</span>
            </div>
            <div class="control-item" v-if="purchaseMode === '收单'">
                <label>收单流动性溢价：</label>
                <el-input-number
                    v-model="liquidityImpact"
                    :min="0"
                    :max="100"
                    :step="0.01"
                    :precision="2"
                    controls-position="right"
                    style="width: 150px;"
                />
                <span style="margin-left: 10px; color: #909399; font-size: 12px;">
                    仅在收单模式生效，0 为关闭，建议 0.1～5.0
                </span>
            </div>
            <div class="control-item" v-if="purchaseMode === '收单'">
                <label>采购时间上限：</label>
                <el-input-number
                    v-model="purchaseTimeLimit"
                    :min="1"
                    :max="30"
                    :step="1"
                    :precision="0"
                    controls-position="right"
                    style="width: 150px;"
                />
                <span class="unit">天</span>
                <span style="margin-left: 10px; color: #909399; font-size: 12px;">
                    用于流动性检查，基于30天平均交易量计算预期交易量
                </span>
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
                    :disabled="useCustomData"
                />
            </div>
            <div class="control-item">
                <label>使用自定义数据：</label>
                <el-switch
                    v-model="useCustomData"
                    active-text="是"
                    inactive-text="否"
                />
            </div>
            <el-button 
                v-if="useCustomData" 
                @click="openImportDialog"
                type="primary"
            >
                导入自定义清单
            </el-button>
            <el-button @click="getCompressedAsteroidData" :loading="loading" type="primary">
                <el-icon :size="18"><Cpu /></el-icon> 求解
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
                                        采购总体积
                                    </div>
                                </template>
                            </el-statistic>
                            <div class="volume-details">
                                <div>矿石: {{ formatAccounting(totalOreVolume) }} m³</div>
                                <div>矿物: {{ formatAccounting(totalMineralVolume) }} m³</div>
                                <div class="volume-total">总计: {{ formatAccounting(totalVolume) }} m³</div>
                            </div>
                        </div>
                    </el-col>
                    <el-col :xs="24" :sm="12" :md="8" :lg="8" :xl="8" class="statistic-col">
                        <div class="statistic-item statistic-item-purchase">
                            <el-statistic 
                                :value="totalPurchaseCost" 
                                :precision="2"
                                suffix=" ISK"
                            >
                                <template #title>
                                    <div class="statistic-title">
                                        <span class="statistic-icon">🛒</span>
                                        采购总价值
                                    </div>
                                </template>
                            </el-statistic>
                            <div class="purchase-details">
                                <div>矿石: {{ formatAccounting(totalCost) }} ISK</div>
                                <div>矿物: {{ formatAccounting(totalMineralCost) }} ISK</div>
                                <div class="purchase-total">总计: {{ formatAccounting(totalPurchaseCost) }} ISK</div>
                            </div>
                        </div>
                    </el-col>
                    <el-col :xs="24" :sm="12" :md="8" :lg="8" :xl="8" class="statistic-col">
                        <div class="statistic-item statistic-item-required">
                            <el-statistic 
                                :value="totalRequiredValue" 
                                :precision="2"
                                suffix=" ISK"
                            >
                                <template #title>
                                    <div class="statistic-title">
                                        <span class="statistic-icon">🎯</span>
                                        需求总价值
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
                    
                    <el-col :xs="24" :sm="12" :md="8" :lg="8" :xl="8" class="statistic-col">
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
                            <div class="produced-details">
                                <div class="discount-ratio">多余价值: {{ formatAccounting(totalExcessValue) }} </div>
                            </div>
                            <div class="produced-details">
                                <div class="discount-ratio">多余比例: {{ formatAccounting(totalExcessValue / totalProducedValue * 100) }}% </div>
                            </div>
                            <div class="produced-details">
                                <div class="discount-ratio">折扣比例: {{ formatAccounting(discountRatio) }}%</div>
                            </div>
                        </div>
                    </el-col>
                    <el-col :xs="24" :sm="12" :md="8" :lg="8" :xl="8" class="statistic-col">
                        <div class="statistic-item statistic-item-total-cost">
                            <el-statistic 
                                :value="totalCostWithShipping" 
                                :precision="2"
                                suffix=" ISK"
                            >
                                <template #title>
                                    <div class="statistic-title">
                                        <span class="statistic-icon">💳</span>
                                        总成本
                                    </div>
                                </template>
                            </el-statistic>
                            <div class="total-cost-details">
                                <div>采购: {{ formatAccounting(totalPurchaseCost) }} ISK</div>
                                <div>运费: {{ formatAccounting(estimatedShippingCost) }} ISK</div>
                                <div class="total-cost-total">总计: {{ formatAccounting(totalCostWithShipping) }} ISK</div>
                                <div class="total-cost-discount">折扣比例: {{ formatAccounting(totalCostDiscountRatio) }}%</div>
                            </div>
                        </div>
                    </el-col>
                </el-row>
            </el-card>
        </div>
        
        <div v-if="compressedAsteroidData && !compressedAsteroidData.is_empty" class="compressed-asteroid-container">
            <el-row :gutter="20">
                <!-- 第一行：矿物对比表格 和 矿石采购表格 -->
                <el-col :xs="24" :sm="24" :md="12" :lg="12" :xl="12" class="layout-item">
                    <!-- 矿物对比表格 -->
                    <div class="mineral-comparison">
                <el-card shadow="never">
                    <template #header>
                        <span>矿物对比</span>
                    </template>
                    <el-table
                        :data="mineralComparisonTableData"
                        border
                        max-height="600"
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
                        <el-table-column label="不足数量" prop="shortage_quantity" width="120">
                            <template #default="{ row }">
                                <span :style="{ color: row.shortage_quantity > 0 ? '#f56c6c' : 'inherit' }">
                                    {{ formatAccounting(row.shortage_quantity) }}
                                </span>
                            </template>
                        </el-table-column>
                        <el-table-column label="不足价值" prop="shortage_value" width="150">
                            <template #header>
                                不足价值 {{ formatAccounting(totalShortageValue) }}
                            </template>
                            <template #default="{ row }">
                                <span :style="{ color: row.shortage_value > 0 ? '#f56c6c' : 'inherit' }">
                                    {{ formatAccounting(row.shortage_value) }}
                                </span>
                            </template>
                        </el-table-column>
                    </el-table>
                </el-card>
                    </div>
                </el-col>
                
                <el-col :xs="24" :sm="24" :md="12" :lg="12" :xl="12" class="layout-item">
                    <!-- 矿石采购表格 -->
                    <div class="ore-purchase">
                <el-card shadow="never">
                    <template #header>
                        <span>矿石采购表</span>
                    </template>
                    <el-table
                        :data="orePurchaseTableData"
                        border
                        max-height="600"
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
                        <el-table-column label="平均价格" prop="avrprice" width="180">
                            <template #default="{ row }">
                                <div>
                                    <div>{{ formatAccounting(row.avrprice) }}</div>
                                    <div
                                        v-if="row.liquidity_premium_rate && row.liquidity_premium_rate > 0"
                                        style="font-size: 12px; color: #909399; margin-top: 2px;"
                                    >
                                        流动性溢价：+{{ formatAccounting(row.liquidity_premium_rate * 100) }}%
                                    </div>
                                </div>
                            </template>
                        </el-table-column>
                        <el-table-column label="总价" prop="total_price" width="150">
                            <template #header>
                                总采购价值 {{ formatAccounting(totalPurchaseCost) }}
                            </template>
                            <template #default="{ row }">
                                {{ formatAccounting(row.total_price) }}
                            </template>
                        </el-table-column>
                        <el-table-column label="产出价值" prop="output_value" width="150">
                            <template #default="{ row }">
                                {{ formatAccounting(row.output_value) }}
                            </template>
                        </el-table-column>
                    </el-table>
                </el-card>
                    </div>
                </el-col>
                
                <!-- 第二行：矿物采购表格 和 桑吉图 -->
                <el-col 
                    :xs="24" 
                    :sm="24" 
                    :md="mineralPurchaseTableData.length > 0 ? 12 : 24" 
                    :lg="mineralPurchaseTableData.length > 0 ? 12 : 24" 
                    :xl="mineralPurchaseTableData.length > 0 ? 12 : 24" 
                    class="layout-item"
                >
                    <!-- 桑吉图 -->
                    <div class="sankey-chart">
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
                </el-col>

                <el-col 
                    v-if="mineralPurchaseTableData.length > 0"
                    :xs="24" 
                    :sm="24" 
                    :md="12" 
                    :lg="12" 
                    :xl="12" 
                    class="layout-item"
                >
                    <!-- 矿物采购表格 -->
                    <div class="mineral-purchase">
                <el-card shadow="never">
                    <template #header>
                        <span>矿物采购表</span>
                    </template>
                    <el-table
                        :data="mineralPurchaseTableData"
                        border
                        max-height="600"
                        show-overflow-tooltip
                        style="font-size: 14px;"
                    >
                        <el-table-column width="70">
                            <template #header>
                                <el-button 
                                    type="primary" 
                                    size="small" 
                                    square
                                    @click="copyMineralData"
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
                        <el-table-column label="矿物名称" prop="name_zh" width="200">
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
                                总价 {{ formatAccounting(totalMineralCost) }}
                            </template>
                            <template #default="{ row }">
                                {{ formatAccounting(row.total_price) }}
                            </template>
                        </el-table-column>
                    </el-table>
                </el-card>
                    </div>
                </el-col>
                

            </el-row>
        </div>
        
        <!-- 导入自定义清单弹窗 -->
        <el-dialog
            v-model="importDialogVisible"
            title="导入自定义清单"
            width="600px"
            :close-on-click-modal="false"
        >
            <div style="margin-bottom: 10px;">
                <p style="color: #606266; font-size: 14px; margin-bottom: 10px;">
                    请输入矿物需求清单，每行格式：矿物名称 数量<br/>
                    例如：类银超金属 Mexallon 50000000
                </p>
                <el-input
                    v-model="importText"
                    type="textarea"
                    :rows="10"
                    placeholder="请输入矿物需求清单..."
                    style="font-family: monospace;"
                />
            </div>
            <template #footer>
                <span class="dialog-footer">
                    <el-button @click="importDialogVisible = false">取消</el-button>
                    <el-button type="primary" @click="parseImportText" :loading="importLoading">
                        确定
                    </el-button>
                </span>
            </template>
        </el-dialog>
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

.statistics-card :deep(.el-row) {
    display: flex;
    flex-wrap: wrap;
    align-items: stretch;
}

.statistic-col {
    margin-bottom: 20px;
    display: flex;
    align-items: stretch;
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
    justify-content: flex-start;
    align-items: center;
    position: relative;
    overflow: hidden;
    box-sizing: border-box;
    width: 100%;
    flex: 1;
    height: 100%;
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

.statistic-item-volume .volume-details {
    font-size: 12px;
    color: #909399;
    margin-top: auto;
    padding-top: 12px;
    text-align: left;
    line-height: 1.6;
    width: 100%;
}

.statistic-item-volume .volume-total {
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin-top: 4px;
}

.statistic-item :deep(.el-statistic) {
    flex: 0 0 auto;
}

.statistic-item :deep(.el-statistic__head) {
    margin-bottom: 12px;
}

.statistic-item-cost {
    border-top-color: #67c23a;
}

.statistic-item-mineral-cost {
    border-top-color: #409eff;
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

.statistic-item-purchase {
    border-top-color: #f093fb;
}

.statistic-item-required {
    border-top-color: #4facfe;
}

.statistic-item-total-cost {
    border-top-color: #9c27b0;
}

.statistic-item-total-cost .total-cost-details {
    font-size: 12px;
    color: #909399;
    margin-top: auto;
    padding-top: 12px;
    text-align: left;
    line-height: 1.6;
    width: 100%;
}

.statistic-item-total-cost .total-cost-total {
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin-top: 4px;
}

.statistic-item-total-cost .total-cost-discount {
    font-weight: 600;
    color: var(--el-color-primary);
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--el-border-color-lighter);
}

.statistic-item-purchase .purchase-details {
    font-size: 12px;
    color: #909399;
    margin-top: auto;
    padding-top: 12px;
    text-align: left;
    line-height: 1.6;
    width: 100%;
}

.statistic-item-purchase .purchase-total {
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin-top: 4px;
}

.statistic-item-produced .produced-details {
    font-size: 12px;
    color: #909399;
    margin-top: auto;
    padding-top: 12px;
    text-align: left;
    line-height: 1.6;
    width: 100%;
}

.statistic-item-produced .discount-ratio {
    font-weight: 600;
    color: var(--el-text-color-primary);
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
    
    .statistic-col:nth-child(3),
    .statistic-col:nth-child(6) {
        margin-bottom: 0;
    }
}

@media (min-width: 992px) {
    .statistic-col {
        margin-bottom: 20px;
    }
    
    .statistic-col:nth-child(3),
    .statistic-col:nth-child(6) {
        margin-bottom: 0;
    }
}

.compressed-asteroid-container {
    margin-top: 20px;
}

.layout-item {
    margin-bottom: 20px;
}

.layout-item:last-child {
    margin-bottom: 0;
}

/* Theme override */
.compressed-asteroid-container,
.layout-item,
.statistics-card,
.statistic-item {
    background: var(--k-color-surface) !important;
    border-color: var(--k-color-border) !important;
    color: var(--k-color-text) !important;
}

.statistic-item {
    box-shadow: var(--k-shadow-sm) !important;
}

.statistic-item:hover {
    box-shadow: var(--k-shadow-md) !important;
    background: color-mix(in srgb, var(--k-color-primary) 8%, var(--k-color-surface-soft)) !important;
}

.statistic-item-volume .volume-details,
.statistic-item-total-cost .total-cost-details,
.statistic-item-purchase .purchase-details,
.statistic-item-produced .produced-details {
    color: var(--k-color-text-secondary) !important;
}

:deep(.el-card),
:deep(.el-card__header),
:deep(.el-card__body),
:deep(.el-form-item__label),
:deep(.el-input__wrapper),
:deep(.el-input-number .el-input__wrapper),
:deep(.el-input-number__decrease),
:deep(.el-input-number__increase),
:deep(.el-table),
:deep(.el-table th.el-table__cell),
:deep(.el-table td.el-table__cell),
:deep(.el-tabs__content) {
    background: var(--k-color-surface) !important;
    border-color: var(--k-color-border) !important;
    color: var(--k-color-text) !important;
}

:deep(.el-table th.el-table__cell) {
    background: var(--k-color-surface-soft) !important;
}

:deep([style*='color: #909399']),
:deep([style*='color:#909399']),
:deep([style*='color: #606266']),
:deep([style*='color:#606266']) {
    color: var(--k-color-text-secondary) !important;
}
</style>
