<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { http } from '@/http'
import IndustryPlanConfigFlowTable from './industryPlanConfigFlowTable.vue'
import { ElMessage } from 'element-plus'
import { VueDraggable } from 'vue-draggable-plus'

interface Props {
    selectedPlan: string
}

const configTypeMap = ref<{ [key: string]: string }>({
  "StructureRigConfig": "建筑插件",
  "StructureAssignConf": "建筑分配",
  "MaterialTagConf": "原材料标记",
  "DefaultBlueprintConf": "缺省蓝图参数",
  "LoadAssetConf": "载入库存",
  "MaxJobSplitCountConf": "最大作业拆分控制"
})

const props = defineProps<Props>()


interface ConfigObject {
    "config_id": number,
    "config_type": string,
    "config_value": object
}
const configFlowConfigList = ref<ConfigObject[]>([])
const getConfigFlowConfigList = async () => {
    const res = await http.get('/EVE/industry/getConfigFlowConfigList')
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    configFlowConfigList.value = data.data
    ElMessage.success("获取配置库配置列表")
}

interface PlanConfigObject {
    "config_id": number,
    "config_index_id": number,
    "config_type": string,
    "config_value": object
}
const configFlowList = ref<PlanConfigObject[]>([])
const getConfigFlowList = async () => {
    const res = await http.post('/EVE/industry/getConfigFlowList', {
        plan_name: props.selectedPlan
    })
    const data = await res.json()
    configFlowList.value = data.data
}

const isConfigInPlan = (configId: number): boolean => {
    return configFlowList.value.some(item => item.config_id === configId)
}

const addConfigToPlan = async (config: PlanConfigObject) => {
    const res = await http.post('/EVE/industry/addConfigToPlan', {
        plan_name: props.selectedPlan,
        config_id: config.config_id
    })
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    ElMessage.success(data.message)
    getConfigFlowList()
    // configFlowManagementVisible.value = false
}

const deleteConfigFlowConfig = async (configId: number) => {
    const res = await http.post('/EVE/industry/deleteConfigFlowConfig', {
        config_id: configId
    })
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    ElMessage.success(data.message)
    getConfigFlowConfigList()
    getConfigFlowList()
}

const saveConfigFlowToPlan = async () => {
    const res = await http.post('/EVE/industry/saveConfigFlowToPlan', {
        plan_name: props.selectedPlan,
        config_list: configFlowList.value
    })
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    ElMessage.success(data.message)
    getConfigFlowList()
}

// ============== 配置库管理 ==============

const configFlowManagementVisible = ref(false)
const openConfigFlowManagement = () => {
    configFlowManagementVisible.value = true
}

const createConfigDrawerVisible = ref(false)
const openCreateConfigDrawer = () => {
    createConfigDrawerVisible.value = true
}

const fetchRecommendedPresetsLoading = ref(false)
const fetchRecommendedPresets = async () => {
    fetchRecommendedPresetsLoading.value = true

    const res = await http.post('/EVE/industry/fetchRecommendedPresets', {
        plan_name: props.selectedPlan
    })
    const data = await res.json()
    console.log("fetchRecommendedPresets data", data)

    fetchRecommendedPresetsLoading.value = false
}

interface KeywordGroup {
    index: number,
    keyword: string,
    keyword_type: string
}
const configForm = ref({
    StructureRigConfig: {
        structure_name: '',
        time_eff_level: 0,
        mater_eff_level: 0
    },
    StructureAssignConf: {
        structure_name: '',
        keyword_groups: [
            {
                index: 0,
                keyword: '',
                keyword_type: ''
            }
        ]
    },
    MaterialTagConf: {
        keyword_groups: [
            {
                index: 0,
                keyword: '',
                keyword_type: ''
            }
        ]
    },
    DefaultBlueprintConf: {
        keyword_groups: [
            {
                index: 0,
                keyword: '',
                keyword_type: ''
            }
        ],
        time_eff: 0,
        mater_eff: 0
    },
    LoadAssetConf: {
        container_tag: ""
    },
    MaxJobSplitCountConf: {
        keyword_groups: [
            {
                index: 0,
                keyword: '',
                keyword_type: ''
            }
        ],
        judge_type: '',
        max_count: 0,
        max_time_day: 0,
        max_time_date: ''
    }
})

const createConfigType = ref('建筑插件')
const createConfig = async () => {
    let config_value = null
    console.log("createConfigType.value", createConfigType.value)
    if (createConfigType.value === 'StructureRigConfig') {
        const structure_item = structureSuggestions.value.find(item => item.structure_name === configForm.value.StructureRigConfig.structure_name)
        if (structure_item) {
            config_value = {
                structure_id: structure_item.structure_id,
                time_eff_level: configForm.value.StructureRigConfig.time_eff_level,
                mater_eff_level: configForm.value.StructureRigConfig.mater_eff_level
            }
        }
    } else if (createConfigType.value === 'StructureAssignConf') {
        config_value = configForm.value.StructureAssignConf
    } else if (createConfigType.value === 'MaterialTagConf') {
        config_value = configForm.value.MaterialTagConf
    } else if (createConfigType.value === 'DefaultBlueprintConf') {
        config_value = configForm.value.DefaultBlueprintConf
    } else if (createConfigType.value === 'LoadAssetConf') {
        const container_permission_item = ContainerPermissionSuggestions.value.find(item => item.tag === configForm.value.LoadAssetConf.container_tag)
        if (container_permission_item) {
            config_value = container_permission_item
        }
        else {
            ElMessage.error("未找到对应的库存许可")
            return
        }
    } else if (createConfigType.value === 'MaxJobSplitCountConf') {
        config_value = configForm.value.MaxJobSplitCountConf
    }
    else {
        ElMessage.error("未找到对应的配置类型")
        return
    }
    console.log("config_value", config_value)
    const res = await http.post('/EVE/industry/createConfigFlowConfig', {
        config_type: createConfigType.value,
        config_value: config_value
    })
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    ElMessage.success(data.message)
    createConfigDrawerVisible.value = false
    getConfigFlowConfigList()
}

const structureSuggestionsCreateFilter = (queryString: string) => {
  return (restaurant: StructureItem) => {
    return (
      restaurant.structure_name.toLowerCase().indexOf(queryString.toLowerCase()) === 0
    )
  }
}

interface StructureItem {
    structure_id: number,
    structure_name: string
}
const structureSuggestions = ref<StructureItem[]>([])
const fetchStructureSuggestions = async (queryString: string, cb: (suggestions: StructureItem[]) => void) => {
    const res = await http.get('/EVE/industry/getStructureList')
    const data = await res.json()

    console.log("data", data)
    structureSuggestions.value = data.data
    const results = queryString
    ? structureSuggestions.value.filter(structureSuggestionsCreateFilter(queryString))
    : []

    console.log("results", results)
    cb(results)
}

const assignTypeOptions = ref([
    { value: 'group', label: 'group' },
    { value: 'meta', label: 'meta' },
    { value: 'blueprint', label: 'blueprint' },
    { value: 'marketGroup', label: 'marketGroup' },
    { value: 'category', label: 'category'}
])

// ===================== 关键字组管理 =====================
const group_keyword_map = ref<{ [key: string]: [] }>({
    'group': [],
    'meta': [],
    'blueprint': [],
    'marketGroup': [],
    'category': []
})

const group_keyword_type = ref('')
const before_fetch_group_suggestions = (keyword_type: string) => {
    console.log("before_fetch_group_suggestions keyword_type", keyword_type)
    group_keyword_type.value = keyword_type
    
}

interface TypeItem {
    value: string
}
const Suggestions = ref<TypeItem[]>([])
const fetchGroupSuggestions = async (queryString: string, cb: (suggestions: TypeItem[]) => void) => {
    // const data = await get_group_suggestions(group_keyword_type.value)
    const res = await http.post('/EVE/industry/getGroupSuggestions', {
        assign_type: group_keyword_type.value,
        query: queryString
    })
    const data = await res.json()
    console.log("data", data)
    Suggestions.value = data.data
    const results = queryString
    ? Suggestions.value : []
    console.log("results", results)

    cb(results)
}
const suggestionFilter = (queryString: string) => {
    return (suggestion: TypeItem) => {
        return suggestion.value.toLowerCase().indexOf(queryString.toLowerCase()) === 0
    }
}

const add_conf_group = (config_type: string) => {
    console.log("add_conf_group config_type", config_type)
    if (config_type === 'StructureAssignConf') {
        configForm.value.StructureAssignConf.keyword_groups.push({
            index: configForm.value.StructureAssignConf.keyword_groups.length,
            keyword: '',
            keyword_type: ''
        })
    } else if (config_type === 'MaterialTagConf') {
        configForm.value.MaterialTagConf.keyword_groups.push({
            index: configForm.value.MaterialTagConf.keyword_groups.length,
            keyword: '',
            keyword_type: ''
        })
    }
    else if (config_type === 'DefaultBlueprintConf') {
        configForm.value.DefaultBlueprintConf.keyword_groups.push({
            index: configForm.value.DefaultBlueprintConf.keyword_groups.length,
            keyword: '',
            keyword_type: ''
        })
    }
    else if (config_type === 'MaxJobSplitCountConf') {
        configForm.value.MaxJobSplitCountConf.keyword_groups.push({
            index: configForm.value.MaxJobSplitCountConf.keyword_groups.length,
            keyword: '',
            keyword_type: ''
        })
    }
}

const delete_conf_group = (config_type: string, index: number) => {
    if (config_type === 'StructureAssignConf') {
        configForm.value.StructureAssignConf.keyword_groups.splice(index, 1)
    } else if (config_type === 'MaterialTagConf') {
        configForm.value.MaterialTagConf.keyword_groups.splice(index, 1)
    } else if (config_type === 'DefaultBlueprintConf') {
        configForm.value.DefaultBlueprintConf.keyword_groups.splice(index, 1)
    }
}

// =======================载入库存管理 =====================
interface ContainerPermissionItem {
    tag: string
}
const ContainerPermissionSuggestions = ref<ContainerPermissionItem[]>([])
const StructureContainerPermissionCreateFilter = (queryString: string) => {
  return (restaurant: ContainerPermissionItem) => {
    return (
      restaurant.tag.toLowerCase().indexOf(queryString.toLowerCase()) === 0
    )
  }
}
const fetchContainerPermissionSuggestions = async (queryString: string, cb: (suggestions: ContainerPermissionItem[]) => void) => {
    const res = await http.post('/EVE/industry/getUserAllContainerPermission', {
        force_refresh: false
    })
    const data = await res.json()
    console.log("fetchContainerPermissionSuggestions data", data)
    ContainerPermissionSuggestions.value = data.data
    
    const results = queryString
    ? ContainerPermissionSuggestions.value.filter(StructureContainerPermissionCreateFilter(queryString))
    : ContainerPermissionSuggestions.value
    cb(results)
}

// =======================最大作业拆分控制管理 =====================

const judgeTypeOptions = ref([
    { value: 'count', label: 'count' },
    { value: 'time', label: 'time' }
])
const judgeTypeMap = ref<{ [key: string]: string }>({
    'count': '最大流程',
    'time': '最长时间'
})

// 格式化 JSON 用于 tooltip 显示（带缩进）
const formatJsonTooltip = (value: any): string => {
    try {
        if (typeof value === 'string') {
            // 如果是字符串，尝试解析为 JSON
            const parsed = JSON.parse(value)
            return JSON.stringify(parsed, null, 2)
        } else if (typeof value === 'object' && value !== null) {
            // 如果是对象，直接格式化
            return JSON.stringify(value, null, 2)
        }
        return String(value)
    } catch (e) {
        // 如果不是有效的 JSON，返回原值
        return String(value)
    }
}

const formatConfigValue = (row_data: any): string => {
    if (row_data.config_type === 'DefaultBlueprintConf') {
        const keywords = row_data.config_value.keyword_groups.map((group: any) => `${group.keyword}(${group.keyword_type})`).join(', ') || 'N/A'
        return `关键词组: ${keywords}, 时间效率: ${row_data.config_value.time_eff}, 材料效率: ${row_data.config_value.mater_eff}`
    } else if (row_data.config_type === 'StructureRigConfig') {
        return `建筑: ${row_data.config_value.structure_name}, 时间效率等级: ${row_data.config_value.time_eff_level}, 材料效率等级: ${row_data.config_value.mater_eff_level}`
    } else if (row_data.config_type === 'StructureAssignConf') {
        const keywords = row_data.config_value.keyword_groups.map((group: any) => `${group.keyword}(${group.keyword_type})`).join(', ') || 'N/A'
        return `建筑: ${row_data.config_value.structure_name}, 关键词组: ${keywords}`
    } else if (row_data.config_type === 'MaterialTagConf') {
        const keywords = row_data.config_value.keyword_groups.map((group: any) => `${group.keyword}(${group.keyword_type})`).join(', ') || 'N/A'
        return `原材料标记: ${keywords}`
    } else if (row_data.config_type === 'LoadAssetConf') {
        return `库存许可: ${row_data.config_value.tag}`
    } else if (row_data.config_type === 'MaxJobSplitCountConf') {
        const keywords = row_data.config_value.keyword_groups.map((group: any) => `${group.keyword}(${group.keyword_type})`).join(', ') || 'N/A'
        return `作业类型: ${keywords}, 判断类型: ${row_data.config_value.judge_type}, 最大数量: ${row_data.config_value.max_count}, 最大时间: ${row_data.config_value.max_time_day}天${row_data.config_value.max_time_date}`
    }
    else {
        return String(row_data.config_value)
    }
}

// 格式化 JSON 用于单元格显示（单行，截断）
const formatJsonDisplay = (value: any): string => {
    try {
        if (typeof value === 'string') {
            const parsed = JSON.parse(value)
            return JSON.stringify(parsed)
        } else if (typeof value === 'object' && value !== null) {
            return JSON.stringify(value)
        }
        return String(value)
    } catch (e) {
        return String(value)
    }
}

// =========================================

onMounted(() => {
    getConfigFlowList()
})

// 监听 selectedPlan 的变化，当变化时重新获取数据
watch(
    () => props.selectedPlan,
    (newPlan) => {
        if (newPlan) {
            getConfigFlowList()
        }
    },
    { immediate: false } // immediate: false 表示不在初始化时执行，因为 onMounted 已经处理了
)
</script>

<template>
<div class="industry-plan-config-flow-container" style="flex-direction: column; height: 100%;" >
<div style="display: flex; flex-direction: row; justify-content: flex-start; flex-wrap: wrap; gap: 8px;">
    <el-button @click="openConfigFlowManagement">
        配置库管理
    </el-button>
    <el-button @click="saveConfigFlowToPlan">
        保存当前配置
    </el-button>
    <el-button @click="getConfigFlowList">
        重置修改
    </el-button>
    <el-button>
        保存为预设
    </el-button>
    <el-button>
        从预设加载
    </el-button>
</div>
<VueDraggable
              v-model="configFlowList"
              target="tbody"
              :animation="150"
            >
<industry-plan-config-flow-table :list="configFlowList" />
</VueDraggable>
</div>

<el-drawer 
    v-model="configFlowManagementVisible"
    resizable
    size="1000px"
    @opened="getConfigFlowConfigList"
>
    <div style="display: flex; flex-direction: column; height: 100%;">
        <div>
            <el-button @click="openCreateConfigDrawer">
                创建配置
            </el-button>
            <el-button @click="fetchRecommendedPresets" :loading="fetchRecommendedPresetsLoading">
                拉取推荐预设
            </el-button>
        </div>
        <div>
            <el-table
            :data="configFlowConfigList"
            >
                <el-table-column label="配置类型" prop="config_type" width="150px">
                    <template #default="{ row }">
                        {{ configTypeMap[row.config_type] }}
                    </template>
                </el-table-column>
                <el-table-column label="配置" prop="config_value">
                    <template #default="{ row }">
                        <el-tooltip
                            placement="top"
                            effect="dark"
                            :raw-content="true"
                        >
                            <template #content>
                                <pre class="json-tooltip-content">{{ formatConfigValue(row) }}</pre>
                            </template>
                            <div class="config-value-cell">
                                {{ formatConfigValue(row) }}
                            </div>
                        </el-tooltip>
                    </template>
                </el-table-column>
                <el-table-column label="操作" prop="action" width="220px">
                    <template #default="{ row }">
                        <el-button type="default" plain @click="addConfigToPlan(row)" disabled v-if="isConfigInPlan(row.config_id)">
                            已经存在于{{ props.selectedPlan }}
                        </el-button>
                        <el-button type="primary" plain @click="addConfigToPlan(row)" v-else>
                            添加到计划{{ props.selectedPlan }}
                        </el-button>
                        <el-button type="danger" plain @click="deleteConfigFlowConfig(row.config_id)">
                            删除
                        </el-button>
                    </template>
                </el-table-column>
            </el-table>
        </div>
    </div>

    <el-drawer
    v-model="createConfigDrawerVisible"
    resizable
    width="500px"
    >
        <el-radio-group v-model="createConfigType" size="large" fill="#6cf">
            <el-radio-button label="建筑插件" value="StructureRigConfig" />
            <el-radio-button label="建筑分配" value="StructureAssignConf" />
            <el-radio-button label="原材料标记" value="MaterialTagConf" />
            <el-radio-button label="缺省蓝图参数" value="DefaultBlueprintConf" />
            <el-radio-button label="载入库存" value="LoadAssetConf" />
            <el-radio-button label="最大作业拆分控制" value="MaxJobSplitCountConf" />
        </el-radio-group>

        <!-- 建筑插件配置 -->
        <el-form :model="configForm.StructureRigConfig" label-width="120px" v-if="createConfigType === 'StructureRigConfig'">
            <el-form-item label="选择建筑">
                <el-autocomplete
                    v-model="configForm.StructureRigConfig.structure_name"
                    :fetch-suggestions="fetchStructureSuggestions"
                    value-key="structure_name"
                />
            </el-form-item>
            <span>0=无插件，1=T1插件，2=T2插件</span>
            <el-form-item label="时间效率等级">
                <el-input-number v-model="configForm.StructureRigConfig.time_eff_level" :min="0" :max="2" placeholder="请输入时间效率等级" />
            </el-form-item>
            <el-form-item label="材料效率等级">
                <el-input-number v-model="configForm.StructureRigConfig.mater_eff_level" :min="0" :max="2" placeholder="请输入材料效率等级" />
            </el-form-item>
        </el-form>

        <!-- 建筑分配配置 -->
        <el-form :model="configForm.StructureAssignConf" label-width="120px" v-else-if="createConfigType === 'StructureAssignConf'">
            <el-form-item label="选择建筑">
                <el-autocomplete
                    v-model="configForm.StructureAssignConf.structure_name"
                    :fetch-suggestions="fetchStructureSuggestions"
                    value-key="structure_name"
                />
            </el-form-item>
            <el-card v-for="group in configForm.StructureAssignConf.keyword_groups" :key="group.index">
            <el-form-item label="分配类型">
                <el-select v-model="group.keyword_type" placeholder="Select" style="width: 240px">
                    <el-option
                    v-for="item in assignTypeOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                    />
                </el-select>
            </el-form-item>
            <el-form-item label="标记关键字">
                <el-autocomplete
                    v-model="group.keyword"
                    :fetch-suggestions="fetchGroupSuggestions"
                    value-key="value"
                    @click="before_fetch_group_suggestions(group.keyword_type)"
                />
            </el-form-item>
            <el-button
            @click="delete_conf_group(createConfigType, group.index)"
            :disabled="configForm.StructureAssignConf.keyword_groups.length === 1">
                删除组
            </el-button>
            </el-card>
            <el-button @click="add_conf_group(createConfigType)">
                增加组
            </el-button>
        </el-form>

        <!-- 原材料标记配置 -->
        <el-form :model="configForm.MaterialTagConf" label-width="120px" v-else-if="createConfigType === 'MaterialTagConf'">
            <el-card v-for="group in configForm.MaterialTagConf.keyword_groups" :key="group.index">
            <el-form-item label="原材料类型">
                <el-select v-model="group.keyword_type" placeholder="Select" style="width: 240px">
                    <el-option
                    v-for="item in assignTypeOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"/>
                </el-select>
            </el-form-item>
            <el-form-item label="标记关键字">
                <el-autocomplete
                    v-model="group.keyword"
                    :fetch-suggestions="fetchGroupSuggestions"
                    value-key="value"
                    @click="before_fetch_group_suggestions(group.keyword_type)"
                />
            </el-form-item>
            <el-button
            @click="delete_conf_group(createConfigType, group.index)"
            :disabled="configForm.MaterialTagConf.keyword_groups.length === 1">
                删除组
            </el-button>
            </el-card>
            <el-button @click="add_conf_group(createConfigType)">
                增加组
            </el-button>
        </el-form>
        
        <!-- 缺省蓝图参数配置 -->
        <el-form :model="configForm.DefaultBlueprintConf" label-width="120px" v-else-if="createConfigType === 'DefaultBlueprintConf'">
            <el-card v-for="group in configForm.DefaultBlueprintConf.keyword_groups" :key="group.index">
            <el-form-item label="蓝图类型">
                <el-select v-model="group.keyword_type" placeholder="Select" style="width: 240px">
                    <el-option
                    v-for="item in assignTypeOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"/>
                </el-select>
            </el-form-item>
            <el-form-item label="标记关键字">
                <el-autocomplete
                    v-model="group.keyword"
                    :fetch-suggestions="fetchGroupSuggestions"
                    value-key="value"
                    @click="before_fetch_group_suggestions(group.keyword_type)"
                />
            </el-form-item>
            <el-button
            @click="delete_conf_group(createConfigType, group.index)"
            :disabled="configForm.DefaultBlueprintConf.keyword_groups.length === 1">
                删除组
            </el-button>
            </el-card>
            <el-button @click="add_conf_group(createConfigType)">
                增加组
            </el-button>

            <el-form-item label="时间效率">
                <el-input-number v-model="configForm.DefaultBlueprintConf.time_eff" placeholder="请输入时间效率" :min="0" :max="20" />
            </el-form-item>
            <el-form-item label="材料效率">
                <el-input-number v-model="configForm.DefaultBlueprintConf.mater_eff" placeholder="请输入材料效率" :min="0" :max="10" />
            </el-form-item>
        </el-form>
        
        <!-- 载入库存配置 -->
        <el-form :model="configForm.LoadAssetConf" label-width="120px" v-else-if="createConfigType === 'LoadAssetConf'">
            <el-form-item label="选择库存许可">
                <el-autocomplete
                    v-model="configForm.LoadAssetConf.container_tag"
                    :fetch-suggestions="fetchContainerPermissionSuggestions"
                    value-key="tag"
                />
            </el-form-item>
        </el-form>

        <!-- 最大作业拆分控制配置 -->
        <el-form :model="configForm.MaxJobSplitCountConf" label-width="120px" v-else-if="createConfigType === 'MaxJobSplitCountConf'">
            <el-card v-for="group in configForm.MaxJobSplitCountConf.keyword_groups" :key="group.index">
            <el-form-item label="作业类型">
                <el-select v-model="group.keyword_type" placeholder="Select" style="width: 240px">
                    <el-option
                    v-for="item in assignTypeOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"/>
                </el-select>
            </el-form-item>
            <el-form-item label="标记关键字">
                <el-autocomplete
                    v-model="group.keyword"
                    :fetch-suggestions="fetchGroupSuggestions"
                    value-key="value"
                    @click="before_fetch_group_suggestions(group.keyword_type)"
                />
            </el-form-item>
            <el-button
            @click="delete_conf_group(createConfigType, group.index)"
            :disabled="configForm.MaxJobSplitCountConf.keyword_groups.length === 1">
                删除组
            </el-button>
            </el-card>
            <el-button @click="add_conf_group(createConfigType)">
                增加组
            </el-button>

            <el-form-item label="判断类型">
                <el-select v-model="configForm.MaxJobSplitCountConf.judge_type" placeholder="Select" style="width: 240px">
                    <el-option
                    v-for="item in judgeTypeOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"/>
                </el-select>
            </el-form-item>
            <el-form-item label="最大流程" v-if="configForm.MaxJobSplitCountConf.judge_type === 'count'">
                <el-input-number v-model="configForm.MaxJobSplitCountConf.max_count" placeholder="请输入最大作业数量" :min="0" />
                <!-- 预估时间 -->
            </el-form-item>
            <el-form-item label="最长时间" v-if="configForm.MaxJobSplitCountConf.judge_type === 'time'">
                <el-input-number v-model="configForm.MaxJobSplitCountConf.max_time_day" placeholder="天" :min="0" :max="100" />
                <span>天</span>
                <el-time-picker v-model="configForm.MaxJobSplitCountConf.max_time_date" placeholder="时间" value-format="HH:mm:ss" />
                <!-- 预估组件制造流程数 -->
            </el-form-item>
        </el-form>

        <template #footer>
            <el-button @click="createConfig" type="primary" plain size="large">创建</el-button>
        </template>
        </el-drawer>
    </el-drawer>
</template>

<style scoped>
.config-value-cell {
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.json-tooltip-content {
    margin: 0;
    padding: 8px;
    background: #1f1f1f;
    color: #fff;
    border-radius: 4px;
    max-width: 500px;
    max-height: 400px;
    overflow: auto;
    font-size: 12px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-all;
}
</style>