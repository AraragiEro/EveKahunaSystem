<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { http } from '@/http'
import type { PlanProductTableData, PlanTableData } from './components/interfaceType.vue'
import { ElMessage } from 'element-plus'

// localStorage key 前缀
const STORAGE_KEY_PREFIX = 'plan_calculate_result_'

// 拉取计划列表
const selectedPlan = ref<string | null>(null)
const planList = ref<PlanTableData[]>([])
const getPlanList = async () => {
    const res = await http.post('/EVE/industry/getPlanTableData')
    const data = await res.json()
    planList.value = data.data
}

// 保存计算结果到本地
const saveToLocal = (planName: string, data: any, keys: string) => {
    try {
        const key = `${STORAGE_KEY_PREFIX}${keys}${planName}`
        localStorage.setItem(key, JSON.stringify(data))
        console.log(`计算结果已保存到本地: ${planName}`)
    } catch (error) {
        console.error('保存到本地失败:', error)
    }
}

// 从本地读取计算结果
const loadFromLocal = (planName: string, keys: string): any[] | null => {
    try {
        const key = `${STORAGE_KEY_PREFIX}${keys}${planName}`
        const data = localStorage.getItem(key)
        if (data) {
            const parsed = JSON.parse(data)
            console.log(`从本地加载计算结果: ${planName}`)
            return parsed
        }
    } catch (error) {
        console.error('从本地读取失败:', error)
    }
    return null
}

// 拉取计划计算结果
const PlanCalculateMaterialTableView = ref<any[]>([])
const PlanCalculateResultTableView = ref<any[]>([])
const getPlanCalculateResultTableView = async () => {
    console.log("getPlanCalculateResultTableView", selectedPlan.value)
    if (!selectedPlan.value) {
        ElMessage.error("请选择计划")
        return
    }
    try {
        
        
        const res = await http.post('/EVE/industry/getPlanCalculateResultTableView',
            {
                plan_name: selectedPlan.value
            }
        )
        
        // 检查 HTTP 响应状态
        if (!res.ok) {
            ElMessage.error(`请求失败: HTTP ${res.status}`)
            return
        }
        
        const data = await res.json()
        
        if (data.status !== 200) {
            ElMessage.error(data.error || "获取数据失败")
            return
        }
        // 先清空数据，避免数据错位
        PlanCalculateResultTableView.value = []
        PlanCalculateMaterialTableView.value = []
        const resultData = data.data || {}
        // 使用 nextTick 确保 DOM 更新完成后再赋值，避免数据错位
        await nextTick()
        PlanCalculateResultTableView.value = resultData.flow_output || []
        PlanCalculateMaterialTableView.value = resultData.material_output || []
        
        // 保存到本地
        saveToLocal(selectedPlan.value, resultData.flow_output, "flow")
        saveToLocal(selectedPlan.value, resultData.material_output, "material")

        ElMessage.success("计算成功")
    } catch (error) {
        console.error("getPlanCalculateResultTableView error:", error)
        ElMessage.error(error instanceof Error ? error.message : "网络请求失败，请稍后重试")
    }
}

// 监听计划选择变化，自动加载本地数据
watch(selectedPlan, (newPlan) => {
    if (newPlan) {
        const localDataFlow = loadFromLocal(newPlan, "flow")
        const localDataMaterial = loadFromLocal(newPlan, "material")
        if (localDataFlow) {
            PlanCalculateResultTableView.value = localDataFlow
        } else {
            PlanCalculateResultTableView.value = []
        }
        if (localDataMaterial) {
            PlanCalculateMaterialTableView.value = localDataMaterial
        } else {
            PlanCalculateMaterialTableView.value = []
        }
    } else {
        PlanCalculateResultTableView.value = []
        PlanCalculateMaterialTableView.value = []
    }
})

onMounted(() => {
    getPlanList()
    // 如果有选中的计划，尝试从本地加载
    if (selectedPlan.value) {
        const localData = loadFromLocal(selectedPlan.value, "flow")
        const localDataMaterial = loadFromLocal(selectedPlan.value, "material")
        if (localData) {
            PlanCalculateResultTableView.value = localData
        }
        if (localDataMaterial) {
            PlanCalculateMaterialTableView.value = localDataMaterial
        }
    }
})

// 会计格式格式化函数
const formatAccounting = (value: number | string | null | undefined): string => {
    if (value === null || value === undefined || value === '') {
        return '0'
    }
    const num = typeof value === 'string' ? parseFloat(value) : value
    if (isNaN(num)) {
        return String(value)
    }
    // 使用 toLocaleString 格式化数字，添加千位分隔符
    return num.toLocaleString('zh-CN', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
    })
}

const lackRowClassName = (data: { row: any, rowIndex: number }) => {
    return data.row.real_quantity > 0 ? 'lack-row' : 'full'
}

</script>

<template>
    <el-row>
        <el-col :span="3">
            <span>选择计划</span>
            <el-select
                v-model="selectedPlan"
                :options="planList"
                :props="{value:'plan_name', label:'plan_name'}"
            />
        </el-col>
        <el-col :span="3">
            <div>
                <el-button @click="getPlanCalculateResultTableView">
                    立刻计算
                </el-button>
            </div>
        </el-col>
            
        <el-col :span="6">
            <span>计算进度</span>
            <el-progress :percentage="50">

            </el-progress>
        </el-col>
    </el-row>
    <el-row>
    <el-tabs style="width: 100%;">
        <el-tab-pane label="表格视图">
            <el-table
                :data="PlanCalculateResultTableView"
                :key="`flow-table-${selectedPlan || 'default'}`"
                row-key="type_id"
                expand-on-click-node="false"
                default-expand-all
                fit
                border
                max-height="75vh"
                show-overflow-tooltip
                :row-class-name="lackRowClassName"
            >
                <el-table-column label="层" prop="layer_id" width="60"/>
                <el-table-column label="物品id" prop="type_id" width="70"/>
                <el-table-column label="物品名en" prop="type_name" width="200"/>
                <el-table-column label="物品名zh" prop="tpye_name_zh" width="200"/>
                <el-table-column label="总需求" prop="quantity" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                <el-table-column label="缺失" prop="real_quantity" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                <el-table-column label="冗余" prop="redundant" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                <el-table-column label="库存" prop="store_quantity" width="100" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                <el-table-column label="运行中任务" prop="running_jobs"/>
                <el-table-column label="缺失流程" prop="real_jobs" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                <el-table-column label="总流程" prop="jobs" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                <el-table-column label="蓝图库存单位" prop="bp_quantity" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                <el-table-column label="蓝图库存流程" prop="bp_jobs" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                <el-table-column label="状态" prop="status" />

            </el-table>
        </el-tab-pane>
        <el-tab-pane label="材料试图">
            <el-table
                :data="PlanCalculateMaterialTableView"
                :key="`material-table-${selectedPlan || 'default'}`"
                row-key="type_id"
                expand-on-click-node="false"
                default-expand-all
                border
                max-height="75vh"
                show-overflow-tooltip
                :row-class-name="lackRowClassName"
            >
                <el-table-column label="类型" prop="layer_id" />
                <el-table-column label="物品id" prop="type_id" />
                <el-table-column label="物品名en" prop="type_name" />
                <el-table-column label="物品名zh" prop="tpye_name_zh" />
                <el-table-column label="缺失" prop="real_quantity" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                <el-table-column label="总需求" prop="quantity" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
                <el-table-column label="库存" prop="store_quantity" :formatter="(row: any, column: any, cellValue: any) => formatAccounting(cellValue)"/>
          </el-table>
        </el-tab-pane>
    </el-tabs>
</el-row>
</template>

<style scoped>
:deep(.el-table .lack-row) {
    background-color: #ff7979 !important;
    font-weight: bold !important;
    color: #000000 !important;
}
</style>