<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'

// 定义接口类型
interface RunningJobData {
    activity_id: number
    activity_name: string
    blueprint_id: number
    blueprint_location_id: number
    blueprint_type_id: number
    character_name: string
    character_title: string
    cost: number
    duration: number
    end_date: string
    facility_id: number
    installer_id: number
    job_id: number
    licensed_runs: number
    location_id: number
    output_location_id: number
    probability: number
    product_type_id: number
    product_type_name: string
    runs: number
    start_date: string
    status: string
}

interface ActivitySummary {
    activity_name: string
    total_duration: number
    total_cost: number
    salary: number
}

interface LaborSummary {
    character_title: string
    character_name: string
    activities: ActivitySummary[]
    total_duration: number
    total_cost: number
    total_salary: number // 总工资（duration计算的工资 + cost）
    salary_only: number // 仅由 duration 计算的工资（不包括 cost）
    salary_percentage: number
}

// Props
const props = defineProps<{
    runningJobs: RunningJobData[]
}>()

// localStorage key
const SALARY_CONFIG_KEY = 'labor_salary_config'

// 工资配置
const salaryConfig = ref<{ [key: string]: number }>({
    '制造': 0,
    '反应': 0
})

// 加载工资配置
const loadSalaryConfig = () => {
    try {
        const saved = localStorage.getItem(SALARY_CONFIG_KEY)
        if (saved) {
            const parsed = JSON.parse(saved)
            salaryConfig.value = { ...salaryConfig.value, ...parsed }
        }
    } catch (error) {
        console.error('加载工资配置失败:', error)
    }
}

// 保存工资配置
const saveSalaryConfig = () => {
    try {
        localStorage.setItem(SALARY_CONFIG_KEY, JSON.stringify(salaryConfig.value))
    } catch (error) {
        console.error('保存工资配置失败:', error)
    }
}

// 监听工资配置变化
watch(salaryConfig, () => {
    saveSalaryConfig()
}, { deep: true })

// 会计格式格式化函数
const formatAccounting = (value: number | string | null | undefined): string => {
    if (value === null || value === undefined || value === '') {
        return '0'
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

// 复制单元格内容
const copyCellContent = async (content: string | number | null | undefined, fieldName: string = '') => {
    try {
        if (content === null || content === undefined || content === '') {
            ElMessage.warning('没有可复制的内容')
            return
        }
        const text = String(content)
        await navigator.clipboard.writeText(text)
        ElMessage.success(`已复制${fieldName ? ` ${fieldName} ` : ' '}到剪贴板`)
    } catch (error) {
        console.error('复制失败:', error)
        ElMessage.error('复制失败，请重试')
    }
}

// 清理 title：删除 HTML 标签和空格
const cleanTitle = (title: string): string => {
    if (!title) return '未知'
    // 删除所有 HTML 标签（<...>）
    let cleaned = title.replace(/<[^>]*>/g, '')
    // 删除所有空格
    cleaned = cleaned.replace(/\s+/g, '')
    return cleaned || '未知'
}

// 计算劳动力汇总
const laborSummary = computed<LaborSummary[]>(() => {
    if (!props.runningJobs || props.runningJobs.length === 0) {
        return []
    }

    // 按 character_title 分组
    const titleMap = new Map<string, {
        character_name: string
        original_title: string
        activities: Map<string, { duration: number, cost: number }>
    }>()

    props.runningJobs.forEach((job: RunningJobData) => {
        const originalTitle = job.character_title || '未知'
        const title = cleanTitle(originalTitle)
        const activityName = job.activity_name || '未知'
        const duration = job.duration || 0
        const cost = job.cost || 0

        if (!titleMap.has(title)) {
            titleMap.set(title, {
                character_name: job.character_name || '',
                original_title: originalTitle,
                activities: new Map()
            })
        }

        const titleData = titleMap.get(title)!
        if (!titleData.activities.has(activityName)) {
            titleData.activities.set(activityName, { duration: 0, cost: 0 })
        }

        const activityData = titleData.activities.get(activityName)!
        activityData.duration += duration
        activityData.cost += cost
    })

    // 转换为数组并计算工资
    const result: LaborSummary[] = []
    let totalSalary = 0

    titleMap.forEach((titleData, title) => {
        const activities: ActivitySummary[] = []
        let totalDuration = 0
        let totalCost = 0
        let totalSalaryForTitle = 0
        let salaryOnlyForTitle = 0 // 仅由 duration 计算的工资

        titleData.activities.forEach((activityData, activityName) => {
            const dailySalary = salaryConfig.value[activityName] || 0
            const salaryPerSecond = dailySalary / 86400
            const salaryFromDuration = activityData.duration * salaryPerSecond // 仅由 duration 计算的工资
            const salary = salaryFromDuration + activityData.cost // 总工资（duration计算的工资 + cost）

            activities.push({
                activity_name: activityName,
                total_duration: activityData.duration,
                total_cost: activityData.cost,
                salary: salary
            })

            totalDuration += activityData.duration
            totalCost += activityData.cost
            totalSalaryForTitle += salary
            salaryOnlyForTitle += salaryFromDuration
        })

        result.push({
            character_title: title, // 显示清理后的 title（不含 HTML 和空格）
            character_name: titleData.character_name,
            activities: activities,
            total_duration: totalDuration,
            total_cost: totalCost,
            total_salary: totalSalaryForTitle,
            salary_only: salaryOnlyForTitle, // 仅由 duration 计算的工资
            salary_percentage: 0 // 稍后计算
        })

        totalSalary += totalSalaryForTitle
    })

    // 计算占比
    result.forEach(item => {
        item.salary_percentage = totalSalary > 0 ? (item.total_salary / totalSalary) * 100 : 0
    })

    // 按总工资降序排序
    result.sort((a, b) => b.total_salary - a.total_salary)

    return result
})

// 图表相关
const salaryChartRef = ref<HTMLElement>()
const costSalaryChartRef = ref<HTMLElement>()
let salaryChartInstance: echarts.ECharts | null = null
let costSalaryChartInstance: echarts.ECharts | null = null

// 初始化工资占比饼图
const initSalaryChart = () => {
    if (!salaryChartRef.value) return
    
    // 如果数据为空，不初始化图表
    if (!laborSummary.value || laborSummary.value.length === 0) {
        if (salaryChartInstance) {
            salaryChartInstance.dispose()
            salaryChartInstance = null
        }
        return
    }

    // 如果图表实例不存在，创建新实例
    if (!salaryChartInstance) {
        salaryChartInstance = echarts.init(salaryChartRef.value)
    }

    const data = laborSummary.value.map(item => ({
        name: item.character_title,
        value: item.total_salary
    }))

    const option: EChartsOption = {
        title: {
            text: '工资占比',
            left: 'center',
            textStyle: {
                fontSize: 16
            }
        },
        tooltip: {
            trigger: 'item',
            formatter: (params: any) => {
                const percentage = ((params.value / laborSummary.value.reduce((sum, item) => sum + item.total_salary, 0)) * 100).toFixed(2)
                return `${params.name}<br/>工资: ${formatAccounting(params.value)}<br/>占比: ${percentage}%`
            }
        },
        legend: {
            orient: 'vertical',
            left: 'left',
            top: 'middle'
        },
        series: [
            {
                name: '工资占比',
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
                        const percentage = ((params.value / laborSummary.value.reduce((sum, item) => sum + item.total_salary, 0)) * 100).toFixed(1)
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
                data: data
            }
        ]
    }

    salaryChartInstance.setOption(option, true) // 使用 notMerge=true 确保完全更新
    // 确保图表正确渲染
    salaryChartInstance.resize()
}

// 初始化 cost 和工资占比饼图
const initCostSalaryChart = () => {
    if (!costSalaryChartRef.value) return
    
    // 如果数据为空，不初始化图表
    if (!laborSummary.value || laborSummary.value.length === 0) {
        if (costSalaryChartInstance) {
            costSalaryChartInstance.dispose()
            costSalaryChartInstance = null
        }
        return
    }

    // 如果图表实例不存在，创建新实例
    if (!costSalaryChartInstance) {
        costSalaryChartInstance = echarts.init(costSalaryChartRef.value)
    }

    // 将每个个体的成本和工资展开为饼图数据
    const chartData: Array<{ name: string, value: number, itemStyle?: { color: string } }> = []
    laborSummary.value.forEach(item => {
        // 添加成本数据
        chartData.push({
            name: `${item.character_title} - 成本`,
            value: item.total_cost,
            itemStyle: {
                color: '#409EFF' // 蓝色表示成本
            }
        })
        // 添加工资数据（仅由 duration 计算的工资，不包括 cost）
        chartData.push({
            name: `${item.character_title} - 工资`,
            value: item.salary_only,
            itemStyle: {
                color: '#67C23A' // 绿色表示工资
            }
        })
    })

    const total = chartData.reduce((sum, d) => sum + d.value, 0)

    const option: EChartsOption = {
        title: {
            text: '成本与工资占比',
            left: 'center',
            textStyle: {
                fontSize: 16
            }
        },
        tooltip: {
            trigger: 'item',
            formatter: (params: any) => {
                const percentage = ((params.value / total) * 100).toFixed(2)
                return `${params.name}<br/>数值: ${formatAccounting(params.value)}<br/>占比: ${percentage}%`
            }
        },
        legend: {
            show: false // 隐藏自动生成的图例
        },
        graphic: [
            // 手动绘制成本图例
            {
                type: 'group',
                left: '5%',
                top: '45%',
                children: [
                    {
                        type: 'circle',
                        shape: {
                            r: 6
                        },
                        style: {
                            fill: '#409EFF'
                        },
                        x: 0,
                        y: 0
                    },
                    {
                        type: 'text',
                        style: {
                            text: '成本',
                            fill: '#333',
                            fontSize: 14
                        },
                        x: 15,
                        y: -6
                    }
                ]
            },
            // 手动绘制工资图例
            {
                type: 'group',
                left: '5%',
                top: '55%',
                children: [
                    {
                        type: 'circle',
                        shape: {
                            r: 6
                        },
                        style: {
                            fill: '#67C23A'
                        },
                        x: 0,
                        y: 0
                    },
                    {
                        type: 'text',
                        style: {
                            text: '工资',
                            fill: '#333',
                            fontSize: 14
                        },
                        x: 15,
                        y: -6
                    }
                ]
            }
        ],
        series: [
            {
                name: '成本与工资',
                type: 'pie',
                radius: ['40%', '70%'],
                center: ['50%', '50%'],
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
                        // 显示"成本"或"工资"以及占比
                        if (params.name.includes(' - 成本')) {
                            return `成本\n${percentage}%`
                        } else if (params.name.includes(' - 工资')) {
                            return `工资\n${percentage}%`
                        }
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

    costSalaryChartInstance.setOption(option, true) // 使用 notMerge=true 确保完全更新
    // 确保图表正确渲染
    costSalaryChartInstance.resize()
}

// 更新图表
const updateCharts = async () => {
    await nextTick()
    // 确保容器已经渲染并有尺寸
    if (salaryChartRef.value && costSalaryChartRef.value) {
        const salaryContainer = salaryChartRef.value
        const costContainer = costSalaryChartRef.value
        
        // 检查容器是否有尺寸
        if (salaryContainer.offsetWidth > 0 && costContainer.offsetWidth > 0) {
            initSalaryChart()
            initCostSalaryChart()
        } else {
            // 如果容器还没有尺寸，等待一下再试
            setTimeout(() => {
                if (salaryContainer.offsetWidth > 0 && costContainer.offsetWidth > 0) {
                    initSalaryChart()
                    initCostSalaryChart()
                } else {
                    // 如果还是没尺寸，再等待一次
                    setTimeout(() => {
                        initSalaryChart()
                        initCostSalaryChart()
                    }, 200)
                }
            }, 100)
        }
    }
}

// 监听数据变化
watch(() => props.runningJobs, () => {
    updateCharts()
}, { deep: true, immediate: false })

watch(laborSummary, () => {
    // 当数据准备好时更新图表
    if (laborSummary.value && laborSummary.value.length > 0) {
        updateCharts()
    }
}, { deep: true, immediate: false })

watch(salaryConfig, () => {
    updateCharts()
}, { deep: true, immediate: false })

// 监听容器尺寸变化，确保图表能正确初始化
const observeContainer = () => {
    if (salaryChartRef.value && costSalaryChartRef.value) {
        const observer = new ResizeObserver(() => {
            // 当容器尺寸变化时，如果图表已初始化，重新调整大小
            if (salaryChartInstance) {
                salaryChartInstance.resize()
            }
            if (costSalaryChartInstance) {
                costSalaryChartInstance.resize()
            }
        })
        
        observer.observe(salaryChartRef.value)
        observer.observe(costSalaryChartRef.value)
        
        return observer
    }
    return null
}

// 窗口大小调整处理函数
const handleResize = () => {
    salaryChartInstance?.resize()
    costSalaryChartInstance?.resize()
}

// ResizeObserver 实例
let containerObserver: ResizeObserver | null = null

// 组件挂载
onMounted(async () => {
    loadSalaryConfig()
    
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
    if (salaryChartInstance) {
        salaryChartInstance.dispose()
        salaryChartInstance = null
    }
    if (costSalaryChartInstance) {
        costSalaryChartInstance.dispose()
        costSalaryChartInstance = null
    }
    // 移除事件监听
    window.removeEventListener('resize', handleResize)
})
</script>

<template>
    <div class="labor-view">
        <!-- 工资配置区域 -->
        <el-card shadow="never" class="config-card">
            <template #header>
                <div class="card-header">
                    <span>工资配置（每天工资）</span>
                </div>
            </template>
            <el-form :inline="false">
                <el-row :gutter="20">
                    <el-col :span="12">
                        <el-form-item label="制造业工资">
                            <el-input-number
                                v-model="salaryConfig['制造']"
                                :min="0"
                                :precision="2"
                                :step="1000"
                                style="width: 100%"
                                placeholder="请输入每天工资"
                            />
                        </el-form-item>
                    </el-col>
                    <el-col :span="12">
                        <el-form-item label="反应工资">
                            <el-input-number
                                v-model="salaryConfig['反应']"
                                :min="0"
                                :precision="2"
                                :step="1000"
                                style="width: 100%"
                                placeholder="请输入每天工资"
                            />
                        </el-form-item>
                    </el-col>
                </el-row>
            </el-form>
        </el-card>

        <!-- 工资表格 -->
        <el-card shadow="never" class="table-card">
            <template #header>
                <div class="card-header">
                    <span>劳动力工资汇总</span>
                </div>
            </template>
            <el-table
                :data="laborSummary"
                border
                max-height="400px"
                show-overflow-tooltip
            >
                <el-table-column label="个体名称" prop="character_title" width="200">
                    <template #default="{ row }">
                        <div 
                            class="copyable-cell" 
                            @click="copyCellContent(row.character_title, '个体名称')"
                            :title="`点击复制: ${row.character_title || ''}`"
                        >
                            {{ row.character_title }}
                        </div>
                    </template>
                </el-table-column>
                <el-table-column label="角色名" prop="character_name" width="150">
                    <template #default="{ row }">
                        <div 
                            class="copyable-cell" 
                            @click="copyCellContent(row.character_name, '角色名')"
                            :title="`点击复制: ${row.character_name || ''}`"
                        >
                            {{ row.character_name }}
                        </div>
                    </template>
                </el-table-column>
                <el-table-column label="总工资" prop="total_salary" width="150">
                    <template #default="{ row }">
                        <div 
                            class="copyable-cell" 
                            @click="copyCellContent(row.total_salary, '总工资')"
                            :title="`点击复制: ${formatAccounting(row.total_salary)}`"
                        >
                            {{ formatAccounting(row.total_salary) }}
                        </div>
                    </template>
                </el-table-column>
                <el-table-column label="工资" prop="salary_only" width="150">
                    <template #default="{ row }">
                        <div 
                            class="copyable-cell" 
                            @click="copyCellContent(row.salary_only, '工资')"
                            :title="`点击复制: ${formatAccounting(row.salary_only)}`"
                        >
                            {{ formatAccounting(row.salary_only) }}
                        </div>
                    </template>
                </el-table-column>
                <el-table-column label="总成本" prop="total_cost" width="150">
                    <template #default="{ row }">
                        <div 
                            class="copyable-cell" 
                            @click="copyCellContent(row.total_cost, '总成本')"
                            :title="`点击复制: ${formatAccounting(row.total_cost)}`"
                        >
                            {{ formatAccounting(row.total_cost) }}
                        </div>
                    </template>
                </el-table-column>
                <el-table-column label="总时长(秒)" prop="total_duration" width="150">
                    <template #default="{ row }">
                        <div 
                            class="copyable-cell" 
                            @click="copyCellContent(row.total_duration, '总时长')"
                            :title="`点击复制: ${formatAccounting(row.total_duration)}`"
                        >
                            {{ formatAccounting(row.total_duration) }}
                        </div>
                    </template>
                </el-table-column>
                <el-table-column label="工资占比" prop="salary_percentage" width="120">
                    <template #default="{ row }">
                        <div 
                            class="copyable-cell" 
                            @click="copyCellContent(row.salary_percentage.toFixed(2), '工资占比')"
                            :title="`点击复制: ${row.salary_percentage.toFixed(2)}%`"
                        >
                            {{ row.salary_percentage.toFixed(2) }}%
                        </div>
                    </template>
                </el-table-column>
                <el-table-column label="工种详情" prop="activities" min-width="200">
                    <template #default="{ row }">
                        <div v-for="activity in row.activities" :key="activity.activity_name" class="activity-item">
                            <span class="activity-name">{{ activity.activity_name }}:</span>
                            <span class="activity-value">工资 {{ formatAccounting(activity.salary) }}, </span>
                            <span class="activity-value">成本 {{ formatAccounting(activity.total_cost) }}, </span>
                            <span class="activity-value">时长 {{ formatAccounting(activity.total_duration) }}s</span>
                        </div>
                    </template>
                </el-table-column>
            </el-table>
        </el-card>

        <!-- 图表区域 -->
        <el-row :gutter="20" class="charts-row">
            <el-col :span="12">
                <el-card shadow="never" class="chart-card">
                    <div ref="salaryChartRef" class="chart-container"></div>
                </el-card>
            </el-col>
            <el-col :span="12">
                <el-card shadow="never" class="chart-card">
                    <div ref="costSalaryChartRef" class="chart-container"></div>
                </el-card>
            </el-col>
        </el-row>
    </div>
</template>

<style scoped>
.labor-view {
    padding: 20px;
}

.config-card,
.table-card,
.chart-card {
    margin-bottom: 20px;
    border-radius: 8px;
    border: 1px solid #e4e7ed;
}

.card-header {
    font-size: 16px;
    font-weight: 600;
    color: #303133;
}

.copyable-cell {
    cursor: pointer;
    user-select: none;
    padding: 4px 8px;
    margin: -4px -8px;
    border-radius: 4px;
    transition: all 0.2s;
}

.copyable-cell:hover {
    background-color: #f0f9ff;
    color: #409eff;
}

.copyable-cell:active {
    background-color: #e1f5ff;
    transform: scale(0.98);
}

.activity-item {
    margin-bottom: 4px;
    font-size: 12px;
}

.activity-name {
    font-weight: 600;
    color: #606266;
    margin-right: 4px;
}

.activity-value {
    color: #909399;
    margin-right: 8px;
}

.charts-row {
    margin-top: 20px;
}

.chart-container {
    width: 100%;
    height: 400px;
}

:deep(.el-form-item) {
    margin-bottom: 0;
}
</style>

