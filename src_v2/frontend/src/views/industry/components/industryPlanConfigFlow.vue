<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { http } from '@/http'
import IndustryPlanConfigFlowTable from './industryPlanConfigFlowTable.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VueDraggable } from 'vue-draggable-plus'
import { haveRole } from '@/router/guards'
import { useAuthStore } from '@/stores/auth'
import { Setting, Document, RefreshLeft, Operation, DocumentAdd, FolderOpened, Tools, Edit, Share, Delete, Sort } from '@element-plus/icons-vue'

const authStore = useAuthStore()
interface Props {
    selectedPlan: string
}

const haveAlphaRole = computed(() => {
    console.log("roles", authStore.user?.roles)
    return authStore.user?.roles.includes('vip_alpha') || false
})
const haveAdminRole = computed(() => {
    return authStore.user?.roles.includes('admin') || false
})

const configTypeMap = ref<{ [key: string]: string }>({
    "StructureRigConfig": "建筑插件",
    "StructureAssignConf": "建筑分配",
    "MaterialTagConf": "原材料标记",
    "DefaultBlueprintConf": "缺省蓝图参数",
    "LoadAssetConf": "载入库存",
    "MaxJobSplitCountConf": "最大作业拆分控制"
})

const props = defineProps<Props>()

// 获取计划信息（包含user_name）
const getPlanInfo = async () => {
    try {
        const res = await http.post('/EVE/industry/getPlanTableData')
        const data = await res.json()
        if (data.status === 200) {
            const plan = data.data.find((p: any) => {
                // 兼容两种 selectedPlan 形式：
                // 1. 普通用户：props.selectedPlan === plan_name
                // 2. 管理员：props.selectedPlan === `${user_name}:${plan_name}`
                const matchByPlanName = p.plan_name === props.selectedPlan
                const compositeName = `${p.user_name}:${p.plan_name}`
                const matchByComposite = compositeName === props.selectedPlan
                return matchByPlanName || matchByComposite
            })
            return plan ? { user_name: plan.user_name, plan_name: plan.plan_name } : null
        }
    } catch (error) {
        console.error('获取计划信息失败:', error)
    }
    return null
}

interface ConfigObject {
    "config_id": number,
    "config_tag"?: string,
    "config_type": string,
    "config_value": object
}
const configFlowConfigList = ref<ConfigObject[]>([])
const getConfigFlowConfigList = async () => {
    const planInfo = await getPlanInfo()
    const params: any = {}
    if (haveAdminRole.value && planInfo && planInfo.user_name !== authStore.user?.username) {
        params.user_name = planInfo.user_name
    }
    const res = await http.get('/EVE/industry/getConfigFlowConfigList', params)
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
    "config_tag"?: string,
    "config_index_id": number,
    "config_type": string,
    "config_value": object
}
const configFlowList = ref<PlanConfigObject[]>([])
const getConfigFlowList = async () => {
    const planInfo = await getPlanInfo()
    if (!planInfo) {
        ElMessage.error('无法获取计划信息')
        return
    }
    const requestData: any = {
        plan_name: planInfo.plan_name
    }
    if (haveAdminRole.value && planInfo && planInfo.user_name !== authStore.user?.username) {
        requestData.user_name = planInfo.user_name
    }
    const res = await http.post('/EVE/industry/getConfigFlowList', requestData)
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message || '获取配置流列表失败')
        return
    }
    configFlowList.value = data.data
}

const isConfigInPlan = (configId: number): boolean => {
    return configFlowList.value.some(item => item.config_id === configId)
}

const addConfigToPlan = async (config: PlanConfigObject) => {
    const planInfo = await getPlanInfo()
    if (!planInfo) {
        ElMessage.error('无法获取计划信息')
        return
    }
    const requestData: any = {
        plan_name: planInfo.plan_name,
        config_id: config.config_id
    }
    if (haveAdminRole.value && planInfo.user_name !== authStore.user?.username) {
        requestData.user_name = planInfo.user_name
    }
    const res = await http.post('/EVE/industry/addConfigToPlan', requestData)
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
    const planInfo = await getPlanInfo()
    const requestData: any = {
        config_id: configId
    }
    if (haveAdminRole.value && planInfo && planInfo.user_name !== authStore.user?.username) {
        requestData.user_name = planInfo.user_name
    }
    const res = await http.post('/EVE/industry/deleteConfigFlowConfig', requestData)
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
    const planInfo = await getPlanInfo()
    if (!planInfo) {
        ElMessage.error("无法获取计划信息")
        return
    }

    const requestData: any = {
        plan_name: planInfo.plan_name,
        config_list: configFlowList.value
    }
    // 如果是管理员模式且计划属于其他用户，传递 user_name
    if (haveAdminRole.value && planInfo.user_name !== authStore.user?.username) {
        requestData.user_name = planInfo.user_name
    }

    const res = await http.post('/EVE/industry/saveConfigFlowToPlan', requestData)
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

// ============== 保存为预设 ==============
const savePresetDialogVisible = ref(false)
const presetName = ref('')

const openSavePresetDialog = () => {
    presetName.value = ''
    savePresetDialogVisible.value = true
}

const savePreset = async () => {
    if (!presetName.value || presetName.value.trim() === '') {
        ElMessage.error('请输入预设名')
        return
    }

    const trimmedPresetName = presetName.value.trim()

    // 检查是否存在同名预设
    try {
        const checkRes = await http.get('/EVE/industry/getConfigFlowPresets')
        const checkData = await checkRes.json()
        if (checkData.status === 200) {
            const existingPreset = checkData.data.find((p: { preset_name: string }) => p.preset_name === trimmedPresetName)
            if (existingPreset) {
                // 存在同名预设，弹出确认对话框
                try {
                    await ElMessageBox.confirm(
                        `预设名 '${trimmedPresetName}' 已存在，是否覆盖？`,
                        '确认覆盖',
                        {
                            confirmButtonText: '覆盖',
                            cancelButtonText: '取消',
                            type: 'warning',
                        }
                    )
                } catch {
                    // 用户取消，不执行保存
                    return
                }
            }
        }
    } catch (error) {
        // 获取预设列表失败，继续执行保存（让后端处理）
        console.warn('获取预设列表失败，继续保存:', error)
    }

    // 执行保存
    try {
        const res = await http.post('/EVE/industry/saveConfigFlowPreset', {
            preset_name: trimmedPresetName,
            config_list: configFlowList.value
        })
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }
        ElMessage.success(data.message)
        savePresetDialogVisible.value = false
        presetName.value = ''
    } catch (error) {
        ElMessage.error('保存预设失败')
    }
}

// ============== 从预设加载 ==============
const loadPresetDialogVisible = ref(false)
const presetList = ref<Array<{ id: number, preset_name: string, config_list: number[] }>>([])
const selectedPresetId = ref<number | null>(null)
const loadingPresets = ref(false)

const openLoadPresetDialog = async () => {
    loadPresetDialogVisible.value = true
    loadingPresets.value = true
    selectedPresetId.value = null
    presetList.value = []

    try {
        const res = await http.get('/EVE/industry/getConfigFlowPresets')
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            loadingPresets.value = false
            return
        }
        presetList.value = data.data
        loadingPresets.value = false
    } catch (error) {
        ElMessage.error('获取预设列表失败')
        loadingPresets.value = false
    }
}

const loadPreset = async () => {
    if (!selectedPresetId.value) {
        ElMessage.error('请选择预设')
        return
    }

    try {
        const res = await http.post('/EVE/industry/loadConfigFlowPreset', {
            preset_id: selectedPresetId.value,
            plan_name: props.selectedPlan
        })
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }
        ElMessage.success(data.message)
        loadPresetDialogVisible.value = false
        selectedPresetId.value = null
        // 刷新配置流列表
        await getConfigFlowList()
    } catch (error) {
        ElMessage.error('加载预设失败')
    }
}

// ============== 预设管理 ==============
const presetManagementVisible = ref(false)
const presetManagementList = ref<Array<{ id: number, preset_name: string, config_list: number[] }>>([])
const loadingPresetManagement = ref(false)
const editingPresetId = ref<number | null>(null)
const editingPresetName = ref('')

const openPresetManagement = async () => {
    presetManagementVisible.value = true
    await refreshPresetManagementList()
}

const refreshPresetManagementList = async () => {
    loadingPresetManagement.value = true
    try {
        const res = await http.get('/EVE/industry/getConfigFlowPresets')
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            loadingPresetManagement.value = false
            return
        }
        presetManagementList.value = data.data
        loadingPresetManagement.value = false
    } catch (error) {
        ElMessage.error('获取预设列表失败')
        loadingPresetManagement.value = false
    }
}

const startEditPresetName = (preset: { id: number, preset_name: string }) => {
    editingPresetId.value = preset.id
    editingPresetName.value = preset.preset_name
}

const cancelEditPresetName = () => {
    editingPresetId.value = null
    editingPresetName.value = ''
}

const savePresetName = async (presetId: number) => {
    const trimmedName = editingPresetName.value.trim()

    // 前端校验
    if (!trimmedName || trimmedName.length === 0) {
        ElMessage.error('预设名称不能为空')
        return
    }
    if (trimmedName.length > 20) {
        ElMessage.error('预设名称长度不能超过20字符')
        return
    }

    try {
        const res = await http.post('/EVE/industry/updateConfigFlowPresetName', {
            preset_id: presetId,
            preset_name: trimmedName
        })
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }
        ElMessage.success(data.message)
        editingPresetId.value = null
        editingPresetName.value = ''
        await refreshPresetManagementList()
    } catch (error) {
        ElMessage.error('更新预设名称失败')
    }
}

const handlePresetNameKeyup = (event: KeyboardEvent, presetId: number) => {
    if (event.key === 'Enter') {
        savePresetName(presetId)
    } else if (event.key === 'Escape') {
        cancelEditPresetName()
    }
}

const sharePreset = async (presetId: number) => {
    try {
        const res = await http.post('/EVE/industry/shareConfigFlowPreset', {
            preset_id: presetId
        })
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }
        const shareCode = data.share_code

        // 显示分享代码对话框
        await ElMessageBox.alert(
            `分享代码：\n${shareCode}\n\n请复制此代码分享给其他用户`,
            '分享预设',
            {
                confirmButtonText: '复制',
                type: 'info',
                dangerouslyUseHTMLString: false,
                beforeClose: async (action, instance, done) => {
                    if (action === 'confirm') {
                        // 复制到剪贴板
                        try {
                            await navigator.clipboard.writeText(shareCode)
                            ElMessage.success('分享代码已复制到剪贴板')
                        } catch (err) {
                            ElMessage.warning('无法复制到剪贴板，请手动复制')
                        }
                    }
                    done()
                }
            }
        )
    } catch (error) {
        if (error !== 'cancel') {
            ElMessage.error('分享预设失败')
        }
    }
}

const deletePreset = async (presetId: number, presetName: string) => {
    try {
        await ElMessageBox.confirm(
            `确定要删除预设 "${presetName}" 吗？`,
            '确认删除',
            {
                confirmButtonText: '删除',
                cancelButtonText: '取消',
                type: 'warning',
            }
        )

        const res = await http.post('/EVE/industry/deleteConfigFlowPreset', {
            preset_id: presetId
        })
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }
        ElMessage.success(data.message)
        await refreshPresetManagementList()
    } catch (error) {
        if (error !== 'cancel') {
            ElMessage.error('删除预设失败')
        }
    }
}

// ============== 载入分享预设代码 ==============
const loadShareCodeDialogVisible = ref(false)
const shareCodeInput = ref('')

const openLoadShareCodeDialog = () => {
    loadShareCodeDialogVisible.value = true
    shareCodeInput.value = ''
}

const loadShareCode = async () => {
    if (!shareCodeInput.value || shareCodeInput.value.trim() === '') {
        ElMessage.error('请输入分享代码')
        return
    }

    try {
        const res = await http.post('/EVE/industry/loadSharedConfigFlowPreset', {
            share_code: shareCodeInput.value.trim()
        })
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }
        ElMessage.success(data.message)
        loadShareCodeDialogVisible.value = false
        shareCodeInput.value = ''
        // 刷新预设列表和配置库列表
        await refreshPresetManagementList()
        await getConfigFlowConfigList()
    } catch (error) {
        ElMessage.error('载入分享预设失败')
    }
}

// ============== 编辑预设 ==============
const presetEditDialogVisible = ref(false)
const editingPresetIdForEdit = ref<number | null>(null)
const editingPresetConfigList = ref<PlanConfigObject[]>([])
const originalPresetConfigList = ref<PlanConfigObject[]>([])

const openEditPresetDialog = async (presetId: number) => {
    editingPresetIdForEdit.value = presetId
    presetEditDialogVisible.value = true

    try {
        const res = await http.get(`/EVE/industry/getConfigFlowPresetDetail?preset_id=${presetId}`)
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            presetEditDialogVisible.value = false
            return
        }
        editingPresetConfigList.value = data.data.config_list.map((config: any) => ({
            config_id: config.config_id,
            config_tag: config.config_tag,
            config_index_id: 0, // 编辑预设时不需要index_id
            config_type: config.config_type,
            config_value: config.config_value
        }))
        originalPresetConfigList.value = JSON.parse(JSON.stringify(editingPresetConfigList.value))
    } catch (error) {
        ElMessage.error('获取预设详情失败')
        presetEditDialogVisible.value = false
    }
}

const savePresetConfig = async () => {
    if (!editingPresetIdForEdit.value) return

    try {
        const res = await http.post('/EVE/industry/saveConfigFlowPresetConfig', {
            preset_id: editingPresetIdForEdit.value,
            config_list: editingPresetConfigList.value
        })
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }
        ElMessage.success(data.message)
        await refreshPresetManagementList()
    } catch (error) {
        ElMessage.error('保存预设配置失败')
    }
}

const resetPresetEdit = async () => {
    if (!editingPresetIdForEdit.value) return

    try {
        const res = await http.get(`/EVE/industry/getConfigFlowPresetDetail?preset_id=${editingPresetIdForEdit.value}`)
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }
        editingPresetConfigList.value = data.data.config_list.map((config: any) => ({
            config_id: config.config_id,
            config_tag: config.config_tag,
            config_index_id: 0,
            config_type: config.config_type,
            config_value: config.config_value
        }))
        originalPresetConfigList.value = JSON.parse(JSON.stringify(editingPresetConfigList.value))
        ElMessage.success('已重置修改')
    } catch (error) {
        ElMessage.error('重置修改失败')
    }
}

const sortPresetConfigList = () => {
    // 定义6种配置类型的顺序
    const configTypeOrder = [
        "StructureRigConfig",
        "StructureAssignConf",
        "MaterialTagConf",
        "DefaultBlueprintConf",
        "LoadAssetConf",
        "MaxJobSplitCountConf"
    ]

    const configMap = new Map<string, PlanConfigObject[]>()
    configTypeOrder.forEach(type => {
        configMap.set(type, [])
    })

    editingPresetConfigList.value.forEach(config => {
        const type = config.config_type
        if (!configMap.has(type)) {
            configMap.set(type, [])
        }
        configMap.get(type)!.push(config)
    })

    const sortedList: PlanConfigObject[] = []
    configTypeOrder.forEach(type => {
        const configs = configMap.get(type) || []
        sortedList.push(...configs)
    })

    configMap.forEach((configs, type) => {
        if (!configTypeOrder.includes(type)) {
            sortedList.push(...configs)
        }
    })

    editingPresetConfigList.value = sortedList
    ElMessage.success("配置已整理完成")
}

const handleDeleteConfigFromPreset = (item: PlanConfigObject) => {
    const index = editingPresetConfigList.value.findIndex(config => config.config_id === item.config_id)
    if (index !== -1) {
        editingPresetConfigList.value.splice(index, 1)
    }
}

const createConfigDrawerVisible = ref(false)
const openCreateConfigDrawer = () => {
    createConfigDrawerVisible.value = true
}

// ============== 修改配置 ==============
const modifyConfigDrawerVisible = ref(false)
const modifyingConfig = ref<PlanConfigObject | null>(null)
const modifyConfigType = ref('')
const modifyConfigForm = ref({
    config_tag: '',
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

const handleDeleteConfigFlowConfig = (item: PlanConfigObject) => {
    const index = configFlowList.value.findIndex(config => config.config_id === item.config_id)
    if (index !== -1) {
        configFlowList.value.splice(index, 1)
    }
}

const handleModifyConfigFlow = (item: PlanConfigObject) => {
    modifyingConfig.value = item
    modifyConfigType.value = item.config_type

    // 预填充 config_tag（如果本来没有tag，则输入框置空）
    modifyConfigForm.value.config_tag = (item as any).config_tag || ''

    // 预填充表单数据
    const configValue = item.config_value as any

    if (item.config_type === 'StructureRigConfig') {
        modifyConfigForm.value.StructureRigConfig = {
            structure_name: configValue.structure_name || '',
            time_eff_level: configValue.time_eff_level ?? 0,
            mater_eff_level: configValue.mater_eff_level ?? 0
        }
    } else if (item.config_type === 'StructureAssignConf') {
        modifyConfigForm.value.StructureAssignConf = {
            structure_name: configValue.structure_name || '',
            keyword_groups: (configValue.keyword_groups || []).map((kg: any, idx: number) => ({
                index: idx,
                keyword: kg.keyword || '',
                keyword_type: kg.keyword_type || ''
            }))
        }
        if (modifyConfigForm.value.StructureAssignConf.keyword_groups.length === 0) {
            modifyConfigForm.value.StructureAssignConf.keyword_groups = [{
                index: 0,
                keyword: '',
                keyword_type: ''
            }]
        }
    } else if (item.config_type === 'MaterialTagConf') {
        modifyConfigForm.value.MaterialTagConf = {
            keyword_groups: (configValue.keyword_groups || []).map((kg: any, idx: number) => ({
                index: idx,
                keyword: kg.keyword || '',
                keyword_type: kg.keyword_type || ''
            }))
        }
        if (modifyConfigForm.value.MaterialTagConf.keyword_groups.length === 0) {
            modifyConfigForm.value.MaterialTagConf.keyword_groups = [{
                index: 0,
                keyword: '',
                keyword_type: ''
            }]
        }
    } else if (item.config_type === 'DefaultBlueprintConf') {
        modifyConfigForm.value.DefaultBlueprintConf = {
            keyword_groups: (configValue.keyword_groups || []).map((kg: any, idx: number) => ({
                index: idx,
                keyword: kg.keyword || '',
                keyword_type: kg.keyword_type || ''
            })),
            time_eff: configValue.time_eff ?? 0,
            mater_eff: configValue.mater_eff ?? 0
        }
        if (modifyConfigForm.value.DefaultBlueprintConf.keyword_groups.length === 0) {
            modifyConfigForm.value.DefaultBlueprintConf.keyword_groups = [{
                index: 0,
                keyword: '',
                keyword_type: ''
            }]
        }
    } else if (item.config_type === 'LoadAssetConf') {
        modifyConfigForm.value.LoadAssetConf = {
            container_tag: configValue.tag || configValue.container_tag || ''
        }
    } else if (item.config_type === 'MaxJobSplitCountConf') {
        modifyConfigForm.value.MaxJobSplitCountConf = {
            keyword_groups: (configValue.keyword_groups || []).map((kg: any, idx: number) => ({
                index: idx,
                keyword: kg.keyword || '',
                keyword_type: kg.keyword_type || ''
            })),
            judge_type: configValue.judge_type || '',
            max_count: configValue.max_count ?? 0,
            max_time_day: configValue.max_time_day ?? 0,
            max_time_date: configValue.max_time_date || ''
        }
        if (modifyConfigForm.value.MaxJobSplitCountConf.keyword_groups.length === 0) {
            modifyConfigForm.value.MaxJobSplitCountConf.keyword_groups = [{
                index: 0,
                keyword: '',
                keyword_type: ''
            }]
        }
    }

    modifyConfigDrawerVisible.value = true
}

const modifyConfig = async () => {
    if (!modifyingConfig.value) return

    // 验证 config_tag：必须输入至少1字符，限制20字符
    const configTag = modifyConfigForm.value.config_tag?.trim() || ''
    if (configTag.length === 0) {
        ElMessage.error('请输入配置标签（至少1字符）')
        return
    }
    if (configTag.length > 20) {
        ElMessage.error('配置标签长度不能超过20字符')
        return
    }

    let config_value = null
    const configType = modifyConfigType.value

    if (configType === 'StructureRigConfig') {
        if (modifyConfigForm.value.StructureRigConfig.structure_name.includes('虚拟-')) {
            config_value = {
                structure_id: virtualStructureDict.value[modifyConfigForm.value.StructureRigConfig.structure_name],
                time_eff_level: modifyConfigForm.value.StructureRigConfig.time_eff_level,
                mater_eff_level: modifyConfigForm.value.StructureRigConfig.mater_eff_level
            }
        }
        else {
            const structure_item = structureSuggestions.value.find(item => item.structure_name === modifyConfigForm.value.StructureRigConfig.structure_name)
            if (structure_item) {
                config_value = {
                    structure_id: structure_item.structure_id,
                    time_eff_level: modifyConfigForm.value.StructureRigConfig.time_eff_level,
                    mater_eff_level: modifyConfigForm.value.StructureRigConfig.mater_eff_level
                }
            } else {
                // 如果找不到，尝试使用原有配置中的 structure_id
                const originalValue = modifyingConfig.value.config_value as any
                if (originalValue.structure_id) {
                    config_value = {
                        structure_id: originalValue.structure_id,
                        time_eff_level: modifyConfigForm.value.StructureRigConfig.time_eff_level,
                        mater_eff_level: modifyConfigForm.value.StructureRigConfig.mater_eff_level
                    }
                } else {
                    ElMessage.error("未找到对应的建筑")
                    return
                }
            }
        }
    } else if (configType === 'StructureAssignConf') {
        if (modifyConfigForm.value.StructureAssignConf.structure_name.includes('虚拟-')) {
            config_value = {
                structure_id: virtualStructureDict.value[modifyConfigForm.value.StructureAssignConf.structure_name],
                structure_name: modifyConfigForm.value.StructureAssignConf.structure_name,
                keyword_groups: modifyConfigForm.value.StructureAssignConf.keyword_groups
            }
        }
        else {
            const structure_item = structureSuggestions.value.find(item => item.structure_name === modifyConfigForm.value.StructureAssignConf.structure_name)
            if (structure_item) {
                config_value = {
                    structure_id: structure_item.structure_id,
                    structure_name: modifyConfigForm.value.StructureAssignConf.structure_name,
                    keyword_groups: modifyConfigForm.value.StructureAssignConf.keyword_groups
                }
            } else {
                // 如果找不到，尝试使用原有配置中的 structure_id
                const originalValue = modifyingConfig.value.config_value as any
                if (originalValue.structure_id) {
                    config_value = {
                        structure_id: originalValue.structure_id,
                        structure_name: modifyConfigForm.value.StructureAssignConf.structure_name,
                        keyword_groups: modifyConfigForm.value.StructureAssignConf.keyword_groups
                    }
                } else {
                    ElMessage.error("未找到对应的建筑")
                    return
                }
            }
        }
    } else if (configType === 'MaterialTagConf') {
        config_value = modifyConfigForm.value.MaterialTagConf
    } else if (configType === 'DefaultBlueprintConf') {
        config_value = modifyConfigForm.value.DefaultBlueprintConf
    } else if (configType === 'LoadAssetConf') {
        const container_permission_item = ContainerPermissionSuggestions.value.find(item => item.tag === modifyConfigForm.value.LoadAssetConf.container_tag)
        if (container_permission_item) {
            config_value = container_permission_item
        }
        else {
            // 如果找不到，尝试使用原有配置
            const originalValue = modifyingConfig.value.config_value as any
            if (originalValue.tag || originalValue.container_tag) {
                config_value = originalValue
                if (modifyConfigForm.value.LoadAssetConf.container_tag) {
                    config_value.tag = modifyConfigForm.value.LoadAssetConf.container_tag
                    config_value.container_tag = modifyConfigForm.value.LoadAssetConf.container_tag
                }
            } else {
                ElMessage.error("未找到对应的库存许可")
                return
            }
        }
    } else if (configType === 'MaxJobSplitCountConf') {
        config_value = modifyConfigForm.value.MaxJobSplitCountConf
    }
    else {
        ElMessage.error("未找到对应的配置类型")
        return
    }

    // 注意：modifyConfigFlowConfig 修改的是配置流配置，不是计划配置流
    // 配置流配置属于用户，但前端无法知道配置属于哪个用户
    // 后端会根据 config_id 查找配置并检查权限，管理员可以绕过权限检查
    // 所以这里不需要传递 user_name，后端会自动处理
    const requestData: any = {
        config_id: modifyingConfig.value.config_id,
        config_value: config_value,
        config_tag: configTag
    }
    const planInfo = await getPlanInfo()
    if (haveAdminRole.value && planInfo && planInfo.user_name !== authStore.user?.username) {
        requestData.user_name = planInfo.user_name
    }

    const res = await http.post('/EVE/industry/modifyConfigFlowConfig', requestData)
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    const modifiedConfigId = modifyingConfig.value.config_id
    const isEditingPreset = presetEditDialogVisible.value

    ElMessage.success(data.message)
    modifyConfigDrawerVisible.value = false
    modifyingConfig.value = null

    // 如果正在编辑预设，更新预设配置列表；否则更新计划配置列表
    if (isEditingPreset && editingPresetConfigList.value.length > 0) {
        // 重新获取配置详情以更新预设配置列表
        await getConfigFlowConfigList()
        // 更新预设配置列表中的对应配置
        const index = editingPresetConfigList.value.findIndex(c => c.config_id === modifiedConfigId)
        if (index !== -1) {
            // 从configFlowConfigList中查找更新后的配置
            const updatedConfig = configFlowConfigList.value.find((c) => c.config_id === modifiedConfigId)
            if (updatedConfig) {
                editingPresetConfigList.value[index] = {
                    config_id: updatedConfig.config_id,
                    config_tag: (updatedConfig as ConfigObject).config_tag || undefined,
                    config_index_id: editingPresetConfigList.value[index].config_index_id,
                    config_type: updatedConfig.config_type,
                    config_value: updatedConfig.config_value
                }
            }
        }
    } else {
        getConfigFlowList()
        getConfigFlowConfigList()
    }
}

const fetchRecommendedPresetsLoading = ref(false)
const fetchRecommendedPresets = async () => {
    fetchRecommendedPresetsLoading.value = true

    const res = await http.get('/EVE/industry/fetchRecommendedPresets', {
        plan_name: props.selectedPlan
    })
    const data = await res.json()
    console.log("fetchRecommendedPresets data", data)

    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    ElMessage.success(data.message)
    getConfigFlowConfigList()
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

const virtualStructureDict = ref<{ [key: string]: number }>({
    "虚拟-Sotiyo": 1,
    "虚拟-Tatara": 2,
    "虚拟-Raitaru": 3,
    "虚拟-Azbel": 4,
    "虚拟-Athanor": 5,
})


const createConfigType = ref('建筑插件')
const createConfig = async () => {
    let config_value = null
    console.log("createConfigType.value", createConfigType.value)
    if (createConfigType.value === 'StructureRigConfig') {
        if (configForm.value.StructureRigConfig.structure_name.includes('虚拟-')) {
            config_value = {
                structure_id: virtualStructureDict.value[configForm.value.StructureRigConfig.structure_name],
                time_eff_level: configForm.value.StructureRigConfig.time_eff_level,
                mater_eff_level: configForm.value.StructureRigConfig.mater_eff_level
            }
        }
        else {
            const structure_item = structureSuggestions.value.find(item => item.structure_name === configForm.value.StructureRigConfig.structure_name)
            if (structure_item) {
                config_value = {
                    structure_id: structure_item.structure_id,
                    time_eff_level: configForm.value.StructureRigConfig.time_eff_level,
                    mater_eff_level: configForm.value.StructureRigConfig.mater_eff_level
                }
            }
        }
    } else if (createConfigType.value === 'StructureAssignConf') {
        if (configForm.value.StructureAssignConf.structure_name.includes('虚拟-')) {
            config_value = {
                structure_id: virtualStructureDict.value[configForm.value.StructureAssignConf.structure_name],
                structure_name: configForm.value.StructureAssignConf.structure_name,
                keyword_groups: configForm.value.StructureAssignConf.keyword_groups
            }
        }
        else {
            const structure_item = structureSuggestions.value.find(item => item.structure_name === configForm.value.StructureAssignConf.structure_name)
            if (structure_item) {
                config_value = {
                    structure_id: structure_item.structure_id,
                    structure_name: configForm.value.StructureAssignConf.structure_name,
                    keyword_groups: configForm.value.StructureAssignConf.keyword_groups
                }
            } else {
                ElMessage.error("未找到对应的建筑")
                return
            }
        }
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
    if (!config_value) {
        ElMessage.error("配置值不能为空")
        return
    }

    console.log("config_value", config_value)
    const requestData: any = {
        config_type: createConfigType.value,
        config_value: config_value
    }
    const planInfo = await getPlanInfo()
    if (haveAdminRole.value && planInfo && planInfo.user_name !== authStore.user?.username) {
        requestData.user_name = planInfo.user_name
    }

    const res = await http.post('/EVE/industry/createConfigFlowConfig', requestData)
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
const structureSuggestionsCache = ref<StructureItem[]>([])
const fetchStructureSuggestions = async (queryString: string, cb: (suggestions: StructureItem[]) => void) => {
    let data: StructureItem[] = []

    if (structureSuggestionsCache.value.length > 0) {
        data = structureSuggestionsCache.value
    } else {
        const res = await http.get('/EVE/industry/getStructureList')
        const response = await res.json()
        if (response.status !== 200) {
            ElMessage.error(response.message)
            data = []
        } else {
            data = response.data || []
        }
        structureSuggestionsCache.value = data
    }

    console.log("data", data)
    structureSuggestions.value = data

    const results = queryString
        ? structureSuggestions.value.filter(structureSuggestionsCreateFilter(queryString))
        : []

    results.push(...Object.keys(virtualStructureDict.value).map(item => ({
        structure_id: virtualStructureDict.value[item],
        structure_name: item
    })))


    console.log("results", results)
    cb(results)
}

const assignTypeOptions = ref([
    { value: 'group', label: '物品组' },
    { value: 'meta', label: 'meta等级' },
    { value: 'blueprint', label: '蓝图' },
    { value: 'marketGroup', label: '市场组' },
    { value: 'category', label: '类别' }
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
    if (data.status !== 200) {
        ElMessage.error(data.message || '获取类型建议失败')
        cb([])
        return
    }
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

// 修改配置的辅助函数
const add_modify_conf_group = (config_type: string) => {
    if (config_type === 'StructureAssignConf') {
        modifyConfigForm.value.StructureAssignConf.keyword_groups.push({
            index: modifyConfigForm.value.StructureAssignConf.keyword_groups.length,
            keyword: '',
            keyword_type: ''
        })
    } else if (config_type === 'MaterialTagConf') {
        modifyConfigForm.value.MaterialTagConf.keyword_groups.push({
            index: modifyConfigForm.value.MaterialTagConf.keyword_groups.length,
            keyword: '',
            keyword_type: ''
        })
    } else if (config_type === 'DefaultBlueprintConf') {
        modifyConfigForm.value.DefaultBlueprintConf.keyword_groups.push({
            index: modifyConfigForm.value.DefaultBlueprintConf.keyword_groups.length,
            keyword: '',
            keyword_type: ''
        })
    } else if (config_type === 'MaxJobSplitCountConf') {
        modifyConfigForm.value.MaxJobSplitCountConf.keyword_groups.push({
            index: modifyConfigForm.value.MaxJobSplitCountConf.keyword_groups.length,
            keyword: '',
            keyword_type: ''
        })
    }
}

const delete_modify_conf_group = (config_type: string, index: number) => {
    if (config_type === 'StructureAssignConf') {
        modifyConfigForm.value.StructureAssignConf.keyword_groups.splice(index, 1)
    } else if (config_type === 'MaterialTagConf') {
        modifyConfigForm.value.MaterialTagConf.keyword_groups.splice(index, 1)
    } else if (config_type === 'DefaultBlueprintConf') {
        modifyConfigForm.value.DefaultBlueprintConf.keyword_groups.splice(index, 1)
    } else if (config_type === 'MaxJobSplitCountConf') {
        modifyConfigForm.value.MaxJobSplitCountConf.keyword_groups.splice(index, 1)
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
    if (data.status !== 200) {
        ElMessage.error(data.message || '获取容器许可建议失败')
        cb([])
        return
    }
    ContainerPermissionSuggestions.value = data.data

    const results = queryString
        ? ContainerPermissionSuggestions.value.filter(StructureContainerPermissionCreateFilter(queryString))
        : ContainerPermissionSuggestions.value
    cb(results)
}

// =======================最大作业拆分控制管理 =====================

const judgeTypeOptions = ref([
    { value: 'count', label: '最大流程' },
    { value: 'time', label: '最长时间' }
])

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

// 一键整理配置：将6种分类的配置各自聚集，但不改变每种配置各自的相对顺序
const sortConfigFlowList = () => {
    // 定义6种配置类型的顺序（按照 configTypeMap 中的顺序）
    const configTypeOrder = [
        "StructureRigConfig",
        "StructureAssignConf",
        "MaterialTagConf",
        "DefaultBlueprintConf",
        "LoadAssetConf",
        "MaxJobSplitCountConf"
    ]

    // 使用 Map 来存储每个类型的配置数组，保持相对顺序
    const configMap = new Map<string, PlanConfigObject[]>()

    // 初始化每个类型的数组
    configTypeOrder.forEach(type => {
        configMap.set(type, [])
    })

    // 遍历 configFlowList，按 config_type 分组，保持相对顺序
    configFlowList.value.forEach(config => {
        const type = config.config_type
        if (!configMap.has(type)) {
            // 如果遇到未知类型，也添加到 Map 中
            configMap.set(type, [])
        }
        configMap.get(type)!.push(config)
    })

    // 按照预定义的顺序，将分组后的配置重新组合
    const sortedList: PlanConfigObject[] = []
    configTypeOrder.forEach(type => {
        const configs = configMap.get(type) || []
        sortedList.push(...configs)
    })

    // 处理可能存在的未知类型配置（虽然理论上不应该有）
    configMap.forEach((configs, type) => {
        if (!configTypeOrder.includes(type)) {
            sortedList.push(...configs)
        }
    })

    // 更新 configFlowList.value 为排序后的结果
    configFlowList.value = sortedList

    ElMessage.success("配置已整理完成")
}

// 紧凑视图模式
const STORAGE_KEY_CONFIGFLOW_CARD_STYLE = 'industry_configflow_card_style_mode'
const getInitialCardStyleMode = (): 'normal' | 'compact' => {
    const saved = localStorage.getItem(STORAGE_KEY_CONFIGFLOW_CARD_STYLE)
    return (saved === 'compact' ? 'compact' : 'normal') as 'normal' | 'compact'
}
const cardStyleMode = ref<'normal' | 'compact'>(getInitialCardStyleMode())

// 切换紧凑视图模式并保存
const handleCardStyleModeChange = (value: 'normal' | 'compact') => {
    cardStyleMode.value = value
    localStorage.setItem(STORAGE_KEY_CONFIGFLOW_CARD_STYLE, value)
}

const configTypeColorMap = ref<{ [key: string]: string }>({
    "StructureRigConfig": "#9fcfff",
    "StructureAssignConf": "#baff97",
    "MaterialTagConf": "#f7d095",
    "DefaultBlueprintConf": "#ffbaba",
    "LoadAssetConf": "#ffe3e3",
    "MaxJobSplitCountConf": "#cacdd3"
})
</script>

<template>
    <div class="industry-plan-config-flow-container">
        <div class="icon-buttons-container">
            <el-tooltip content="配置库管理" placement="top">
                <el-button circle @click="openConfigFlowManagement" type="primary" plain>
                    <el-icon>
                        <Setting />
                    </el-icon>
                </el-button>
            </el-tooltip>
            <el-tooltip content="保存当前配置" placement="top">
                <el-button circle @click="saveConfigFlowToPlan" type="primary" plain>
                    <el-icon>
                        <Document />
                    </el-icon>
                </el-button>
            </el-tooltip>
            <el-tooltip content="重置修改" placement="top">
                <el-button circle @click="getConfigFlowList" type="warning" plain>
                    <el-icon>
                        <RefreshLeft />
                    </el-icon>
                </el-button>
            </el-tooltip>
            <el-tooltip content="整理配置" placement="top">
                <el-button circle @click="sortConfigFlowList" type="info" plain>
                    <el-icon>
                        <Sort />
                    </el-icon>
                </el-button>
            </el-tooltip>
            <el-tooltip content="保存为预设" placement="top">
                <el-button circle @click="openSavePresetDialog" type="info" plain>
                    <el-icon>
                        <DocumentAdd />
                    </el-icon>
                </el-button>
            </el-tooltip>
            <el-tooltip content="从预设加载" placement="top">
                <el-button circle @click="openLoadPresetDialog" type="info" plain>
                    <el-icon>
                        <FolderOpened />
                    </el-icon>
                </el-button>
            </el-tooltip>
            <el-tooltip content="预设管理" placement="top">
                <el-button circle @click="openPresetManagement" type="info" plain>
                    <el-icon>
                        <Tools />
                    </el-icon>
                </el-button>
            </el-tooltip>
            <el-radio-group v-model="cardStyleMode" size="small" @change="handleCardStyleModeChange"
                style="margin-left: 8px;">
                <el-radio-button label="normal">普通</el-radio-button>
                <el-radio-button label="compact">紧凑</el-radio-button>
            </el-radio-group>
        </div>
        <div style="flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column;">
            <VueDraggable v-model="configFlowList" target="tbody" :animation="150" style="height: 100%;">
                <industry-plan-config-flow-table :list="configFlowList" :card-style-mode="cardStyleMode"
                    @modify-config-flow="handleModifyConfigFlow" @delete-config-flow="handleDeleteConfigFlowConfig" />
            </VueDraggable>
        </div>
    </div>

    <el-drawer v-model="configFlowManagementVisible" resizable size="1000px" @opened="getConfigFlowConfigList">
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
                <el-table :data="configFlowConfigList">
                    <el-table-column label="配置类型" prop="config_type" width="150px">
                        <template #default="{ row }">
                            <el-tag :color="configTypeColorMap[row.config_type]" type="plain" size="large"
                                style="font-size: 16px; font-weight: 500;">
                                {{ configTypeMap[row.config_type] }}
                            </el-tag>
                        </template>
                    </el-table-column>
                    <el-table-column label="配置" prop="config_value">
                        <template #default="{ row }">
                            <el-tooltip placement="top" effect="dark" :raw-content="true">
                                <template #content>
                                    <pre class="json-tooltip-content">{{ formatConfigValue(row) }}</pre>
                                </template>
                                <div class="config-value-cell">
                                    {{ row.config_tag || formatConfigValue(row) }}
                                </div>
                            </el-tooltip>
                        </template>
                    </el-table-column>
                    <el-table-column label="操作" prop="action" width="220px">
                        <template #default="{ row }">
                            <el-button type="default" plain @click="addConfigToPlan(row)" disabled
                                v-if="isConfigInPlan(row.config_id)">
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

        <el-drawer v-model="createConfigDrawerVisible" resizable width="700px">
            <el-tooltip placement="left" :width="500" :raw-content="true">
                <template #content>
                    <div style="line-height: 1.8;">
                        <div><strong>蓝图：</strong> 字面意思，针对某一张蓝图进行配置</div>
                        <div><strong>市场组：</strong>某个物品在市场树中的坐标链。</div>
                        <div style="margin-left: 20px;">以Ishtar举例，他的市场组是：Ships → Cruisers → Advanced Cruisers → Heavy
                            Assault Cruisers → Gallente → Ishtar</div>
                        <div style="margin-left: 20px;">如果我选择Cruisers进行筛选，会对所有的巡洋舰生效。如果我选择Heavy Assault
                            Cruisers进行筛选，会对所有的重型突击巡洋舰生效。</div>
                        <div style="margin-left: 20px;">市场组关键词可以对坐标链中出现了关键词的所有物品生效。如果使用Gallente，则会对所有盖伦特的舰船生效。</div>
                        <div style="margin-top: 10px;"><strong>meta等级、物品组、类别</strong> 是EVE物品所拥有的三种属性</div>
                        <div style="margin-left: 20px;">1. meta一般筛选物品的科技等级如T1 T2,势力，死亡空间等</div>
                        <div style="margin-left: 20px;">2. 物品组与类别多种多样，需要使用时随时使用信息功能查询</div>
                        <br>
                        <div>你可以在一个配置中添加多个关键词，关键词之间的关系是与，即必须同时满足。</div>
                        <div>举例：如果我选择meta=Tech II, marketGroup=Ships,则会对所有T2船生效。</div>
                        <div style="margin-top: 10px;"><strong>PS:</strong>
                            左侧的市场树，右键任意物品点击信息，即可查看物品的属性。建议多查看几个物品，利于理解筛选机制。</div>
                    </div>
                </template>
                <el-button type="primary" :icon="Setting"
                    style="margin: 10px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4); font-weight: 600;">
                    如何使用关键词筛选？
                </el-button>
            </el-tooltip>
            <el-radio-group v-model="createConfigType" size="large" fill="#6cf">
                <el-tooltips>
                    <template #content>
                        123
                    </template>
                    <el-radio-button label="建筑插件" value="StructureRigConfig" />
                </el-tooltips>
                <el-radio-button label="建筑分配" value="StructureAssignConf" />
                <el-radio-button label="原材料标记" value="MaterialTagConf" />
                <el-radio-button label="缺省蓝图参数" value="DefaultBlueprintConf" />
                <el-radio-button label="载入库存" value="LoadAssetConf" :disabled="!haveAlphaRole" />
                <el-radio-button label="最大作业拆分控制" value="MaxJobSplitCountConf" />
            </el-radio-group>


            <!-- 建筑插件配置 -->
            <el-form :model="configForm.StructureRigConfig" label-width="120px"
                v-if="createConfigType === 'StructureRigConfig'">
                <el-form-item label="选择建筑">
                    <el-autocomplete v-model="configForm.StructureRigConfig.structure_name"
                        :fetch-suggestions="fetchStructureSuggestions" value-key="structure_name" />
                </el-form-item>
                <span>0=无插件，1=T1插件，2=T2插件</span>
                <el-form-item label="时间效率等级">
                    <el-input-number v-model="configForm.StructureRigConfig.time_eff_level" :min="0" :max="2"
                        placeholder="请输入时间效率等级" />
                </el-form-item>
                <el-form-item label="材料效率等级">
                    <el-input-number v-model="configForm.StructureRigConfig.mater_eff_level" :min="0" :max="2"
                        placeholder="请输入材料效率等级" />
                </el-form-item>
            </el-form>

            <!-- 建筑分配配置 -->
            <el-form :model="configForm.StructureAssignConf" label-width="120px"
                v-else-if="createConfigType === 'StructureAssignConf'">
                <el-form-item label="选择建筑">
                    <el-autocomplete v-model="configForm.StructureAssignConf.structure_name"
                        :fetch-suggestions="fetchStructureSuggestions" value-key="structure_name" />
                </el-form-item>

                <el-card v-for="group in configForm.StructureAssignConf.keyword_groups" :key="group.index">
                    <el-form-item label="分配类型">
                        <el-select v-model="group.keyword_type" placeholder="Select" style="width: 240px">
                            <el-option v-for="item in assignTypeOptions" :key="item.value" :label="item.label"
                                :value="item.value" />
                        </el-select>
                    </el-form-item>

                    <el-form-item label="标记关键字">
                        <el-autocomplete v-model="group.keyword" :fetch-suggestions="fetchGroupSuggestions"
                            value-key="value" @click="before_fetch_group_suggestions(group.keyword_type)" />
                    </el-form-item>
                    <el-button @click="delete_conf_group(createConfigType, group.index)"
                        :disabled="configForm.StructureAssignConf.keyword_groups.length === 1">
                        删除组
                    </el-button>
                </el-card>
                <el-button @click="add_conf_group(createConfigType)">
                    增加组
                </el-button>
            </el-form>

            <!-- 原材料标记配置 -->
            <el-form :model="configForm.MaterialTagConf" label-width="120px"
                v-else-if="createConfigType === 'MaterialTagConf'">
                <el-card v-for="group in configForm.MaterialTagConf.keyword_groups" :key="group.index">
                    <el-form-item label="原材料类型">
                        <el-select v-model="group.keyword_type" placeholder="Select" style="width: 240px">
                            <el-option v-for="item in assignTypeOptions" :key="item.value" :label="item.label"
                                :value="item.value" />
                        </el-select>
                    </el-form-item>
                    <el-form-item label="标记关键字">
                        <el-autocomplete v-model="group.keyword" :fetch-suggestions="fetchGroupSuggestions"
                            value-key="value" @click="before_fetch_group_suggestions(group.keyword_type)" />
                    </el-form-item>
                    <el-button @click="delete_conf_group(createConfigType, group.index)"
                        :disabled="configForm.MaterialTagConf.keyword_groups.length === 1">
                        删除组
                    </el-button>
                </el-card>
                <el-button @click="add_conf_group(createConfigType)">
                    增加组
                </el-button>
            </el-form>

            <!-- 缺省蓝图参数配置 -->
            <el-form :model="configForm.DefaultBlueprintConf" label-width="120px"
                v-else-if="createConfigType === 'DefaultBlueprintConf'">
                <el-card v-for="group in configForm.DefaultBlueprintConf.keyword_groups" :key="group.index">
                    <el-form-item label="蓝图类型">
                        <el-select v-model="group.keyword_type" placeholder="Select" style="width: 240px">
                            <el-option v-for="item in assignTypeOptions" :key="item.value" :label="item.label"
                                :value="item.value" />
                        </el-select>
                    </el-form-item>
                    <el-form-item label="标记关键字">
                        <el-autocomplete v-model="group.keyword" :fetch-suggestions="fetchGroupSuggestions"
                            value-key="value" @click="before_fetch_group_suggestions(group.keyword_type)" />
                    </el-form-item>
                    <el-button @click="delete_conf_group(createConfigType, group.index)"
                        :disabled="configForm.DefaultBlueprintConf.keyword_groups.length === 1">
                        删除组
                    </el-button>
                </el-card>
                <el-button @click="add_conf_group(createConfigType)">
                    增加组
                </el-button>

                <el-form-item label="时间效率">
                    <el-input-number v-model="configForm.DefaultBlueprintConf.time_eff" placeholder="请输入时间效率" :min="0"
                        :max="20" />
                </el-form-item>
                <el-form-item label="材料效率">
                    <el-input-number v-model="configForm.DefaultBlueprintConf.mater_eff" placeholder="请输入材料效率" :min="0"
                        :max="10" />
                </el-form-item>
            </el-form>

            <!-- 载入库存配置 -->
            <el-form :model="configForm.LoadAssetConf" label-width="120px"
                v-else-if="createConfigType === 'LoadAssetConf'">
                <el-form-item label="选择库存许可">
                    <el-autocomplete v-model="configForm.LoadAssetConf.container_tag"
                        :fetch-suggestions="fetchContainerPermissionSuggestions" value-key="tag" />
                </el-form-item>
            </el-form>

            <!-- 最大作业拆分控制配置 -->
            <el-form :model="configForm.MaxJobSplitCountConf" label-width="120px"
                v-else-if="createConfigType === 'MaxJobSplitCountConf'">
                <el-card v-for="group in configForm.MaxJobSplitCountConf.keyword_groups" :key="group.index">
                    <el-form-item label="作业类型">
                        <el-select v-model="group.keyword_type" placeholder="Select" style="width: 240px">
                            <el-option v-for="item in assignTypeOptions" :key="item.value" :label="item.label"
                                :value="item.value" />
                        </el-select>
                    </el-form-item>
                    <el-form-item label="标记关键字">
                        <el-autocomplete v-model="group.keyword" :fetch-suggestions="fetchGroupSuggestions"
                            value-key="value" @click="before_fetch_group_suggestions(group.keyword_type)" />
                    </el-form-item>
                    <el-button @click="delete_conf_group(createConfigType, group.index)"
                        :disabled="configForm.MaxJobSplitCountConf.keyword_groups.length === 1">
                        删除组
                    </el-button>
                </el-card>
                <el-button @click="add_conf_group(createConfigType)">
                    增加组
                </el-button>

                <el-form-item label="判断类型">
                    <el-select v-model="configForm.MaxJobSplitCountConf.judge_type" placeholder="Select"
                        style="width: 240px">
                        <el-option v-for="item in judgeTypeOptions" :key="item.value" :label="item.label"
                            :value="item.value" />
                    </el-select>
                </el-form-item>
                <el-form-item label="最大流程" v-if="configForm.MaxJobSplitCountConf.judge_type === 'count'">
                    <el-input-number v-model="configForm.MaxJobSplitCountConf.max_count" placeholder="请输入最大作业数量"
                        :min="0" />
                    <!-- 预估时间 -->
                </el-form-item>
                <el-form-item label="最长时间" v-if="configForm.MaxJobSplitCountConf.judge_type === 'time'">
                    <el-input-number v-model="configForm.MaxJobSplitCountConf.max_time_day" placeholder="天" :min="0"
                        :max="100" />
                    <span>天</span>
                    <el-time-picker v-model="configForm.MaxJobSplitCountConf.max_time_date" placeholder="时间"
                        value-format="HH:mm:ss" />
                    <!-- 预估组件制造流程数 -->
                </el-form-item>
            </el-form>

            <template #footer>
                <el-button @click="createConfig" type="primary" plain size="large">创建</el-button>
            </template>
        </el-drawer>
    </el-drawer>

    <!-- 修改配置抽屉 -->
    <el-drawer v-model="modifyConfigDrawerVisible" resizable width="500px" title="修改配置">
        <div style="margin-bottom: 16px;">
            <el-tag type="info" size="large">{{ configTypeMap[modifyConfigType] }}</el-tag>
        </div>

        <!-- 配置标签 -->
        <el-form :model="modifyConfigForm" label-width="120px" style="margin-bottom: 24px;">
            <el-form-item label="配置标签">
                <el-input v-model="modifyConfigForm.config_tag" placeholder="请输入配置标签（1-20字符）" maxlength="20"
                    show-word-limit />
            </el-form-item>
        </el-form>

        <!-- 建筑插件配置 -->
        <el-form :model="modifyConfigForm.StructureRigConfig" label-width="120px"
            v-if="modifyConfigType === 'StructureRigConfig'">
            <el-form-item label="选择建筑">
                <el-autocomplete v-model="modifyConfigForm.StructureRigConfig.structure_name"
                    :fetch-suggestions="fetchStructureSuggestions" value-key="structure_name" />
            </el-form-item>
            <span>0=无插件，1=T1插件，2=T2插件</span>
            <el-form-item label="时间效率等级">
                <el-input-number v-model="modifyConfigForm.StructureRigConfig.time_eff_level" :min="0" :max="2"
                    placeholder="请输入时间效率等级" />
            </el-form-item>
            <el-form-item label="材料效率等级">
                <el-input-number v-model="modifyConfigForm.StructureRigConfig.mater_eff_level" :min="0" :max="2"
                    placeholder="请输入材料效率等级" />
            </el-form-item>
        </el-form>

        <!-- 建筑分配配置 -->
        <el-form :model="modifyConfigForm.StructureAssignConf" label-width="120px"
            v-else-if="modifyConfigType === 'StructureAssignConf'">
            <el-form-item label="选择建筑">
                <el-autocomplete v-model="modifyConfigForm.StructureAssignConf.structure_name"
                    :fetch-suggestions="fetchStructureSuggestions" value-key="structure_name" />
            </el-form-item>
            <el-card v-for="group in modifyConfigForm.StructureAssignConf.keyword_groups" :key="group.index">
                <el-form-item label="分配类型">
                    <el-select v-model="group.keyword_type" placeholder="Select" style="width: 240px">
                        <el-option v-for="item in assignTypeOptions" :key="item.value" :label="item.label"
                            :value="item.value" />
                    </el-select>
                </el-form-item>
                <el-form-item label="标记关键字">
                    <el-autocomplete v-model="group.keyword" :fetch-suggestions="fetchGroupSuggestions"
                        value-key="value" @click="before_fetch_group_suggestions(group.keyword_type)" />
                </el-form-item>
                <el-button @click="delete_modify_conf_group(modifyConfigType, group.index)"
                    :disabled="modifyConfigForm.StructureAssignConf.keyword_groups.length === 1">
                    删除组
                </el-button>
            </el-card>
            <el-button @click="add_modify_conf_group(modifyConfigType)">
                增加组
            </el-button>
        </el-form>

        <!-- 原材料标记配置 -->
        <el-form :model="modifyConfigForm.MaterialTagConf" label-width="120px"
            v-else-if="modifyConfigType === 'MaterialTagConf'">
            <el-card v-for="group in modifyConfigForm.MaterialTagConf.keyword_groups" :key="group.index">
                <el-form-item label="原材料类型">
                    <el-select v-model="group.keyword_type" placeholder="Select" style="width: 240px">
                        <el-option v-for="item in assignTypeOptions" :key="item.value" :label="item.label"
                            :value="item.value" />
                    </el-select>
                </el-form-item>
                <el-form-item label="标记关键字">
                    <el-autocomplete v-model="group.keyword" :fetch-suggestions="fetchGroupSuggestions"
                        value-key="value" @click="before_fetch_group_suggestions(group.keyword_type)" />
                </el-form-item>
                <el-button @click="delete_modify_conf_group(modifyConfigType, group.index)"
                    :disabled="modifyConfigForm.MaterialTagConf.keyword_groups.length === 1">
                    删除组
                </el-button>
            </el-card>
            <el-button @click="add_modify_conf_group(modifyConfigType)">
                增加组
            </el-button>
        </el-form>

        <!-- 缺省蓝图参数配置 -->
        <el-form :model="modifyConfigForm.DefaultBlueprintConf" label-width="120px"
            v-else-if="modifyConfigType === 'DefaultBlueprintConf'">
            <el-card v-for="group in modifyConfigForm.DefaultBlueprintConf.keyword_groups" :key="group.index">
                <el-form-item label="蓝图类型">
                    <el-select v-model="group.keyword_type" placeholder="Select" style="width: 240px">
                        <el-option v-for="item in assignTypeOptions" :key="item.value" :label="item.label"
                            :value="item.value" />
                    </el-select>
                </el-form-item>
                <el-form-item label="标记关键字">
                    <el-autocomplete v-model="group.keyword" :fetch-suggestions="fetchGroupSuggestions"
                        value-key="value" @click="before_fetch_group_suggestions(group.keyword_type)" />
                </el-form-item>
                <el-button @click="delete_modify_conf_group(modifyConfigType, group.index)"
                    :disabled="modifyConfigForm.DefaultBlueprintConf.keyword_groups.length === 1">
                    删除组
                </el-button>
            </el-card>
            <el-button @click="add_modify_conf_group(modifyConfigType)">
                增加组
            </el-button>

            <el-form-item label="时间效率">
                <el-input-number v-model="modifyConfigForm.DefaultBlueprintConf.time_eff" placeholder="请输入时间效率" :min="0"
                    :max="20" />
            </el-form-item>
            <el-form-item label="材料效率">
                <el-input-number v-model="modifyConfigForm.DefaultBlueprintConf.mater_eff" placeholder="请输入材料效率"
                    :min="0" :max="10" />
            </el-form-item>
        </el-form>

        <!-- 载入库存配置 -->
        <el-form :model="modifyConfigForm.LoadAssetConf" label-width="120px"
            v-else-if="modifyConfigType === 'LoadAssetConf'">
            <el-form-item label="选择库存许可">
                <el-autocomplete v-model="modifyConfigForm.LoadAssetConf.container_tag"
                    :fetch-suggestions="fetchContainerPermissionSuggestions" value-key="tag" />
            </el-form-item>
        </el-form>

        <!-- 最大作业拆分控制配置 -->
        <el-form :model="modifyConfigForm.MaxJobSplitCountConf" label-width="120px"
            v-else-if="modifyConfigType === 'MaxJobSplitCountConf'">
            <el-card v-for="group in modifyConfigForm.MaxJobSplitCountConf.keyword_groups" :key="group.index">
                <el-form-item label="作业类型">
                    <el-select v-model="group.keyword_type" placeholder="Select" style="width: 240px">
                        <el-option v-for="item in assignTypeOptions" :key="item.value" :label="item.label"
                            :value="item.value" />
                    </el-select>
                </el-form-item>
                <el-form-item label="标记关键字">
                    <el-autocomplete v-model="group.keyword" :fetch-suggestions="fetchGroupSuggestions"
                        value-key="value" @click="before_fetch_group_suggestions(group.keyword_type)" />
                </el-form-item>
                <el-button @click="delete_modify_conf_group(modifyConfigType, group.index)"
                    :disabled="modifyConfigForm.MaxJobSplitCountConf.keyword_groups.length === 1">
                    删除组
                </el-button>
            </el-card>
            <el-button @click="add_modify_conf_group(modifyConfigType)">
                增加组
            </el-button>

            <el-form-item label="判断类型">
                <el-select v-model="modifyConfigForm.MaxJobSplitCountConf.judge_type" placeholder="Select"
                    style="width: 240px">
                    <el-option v-for="item in judgeTypeOptions" :key="item.value" :label="item.label"
                        :value="item.value" />
                </el-select>
            </el-form-item>
            <el-form-item label="最大流程" v-if="modifyConfigForm.MaxJobSplitCountConf.judge_type === 'count'">
                <el-input-number v-model="modifyConfigForm.MaxJobSplitCountConf.max_count" placeholder="请输入最大作业数量"
                    :min="0" />
            </el-form-item>
            <el-form-item label="最长时间" v-if="modifyConfigForm.MaxJobSplitCountConf.judge_type === 'time'">
                <el-input-number v-model="modifyConfigForm.MaxJobSplitCountConf.max_time_day" placeholder="天" :min="0"
                    :max="100" />
                <span>天</span>
                <el-time-picker v-model="modifyConfigForm.MaxJobSplitCountConf.max_time_date" placeholder="时间"
                    value-format="HH:mm:ss" />
            </el-form-item>
        </el-form>

        <template #footer>
            <el-button @click="modifyConfig" type="primary" plain size="large">保存修改</el-button>
        </template>
    </el-drawer>

    <!-- 保存为预设对话框 -->
    <el-dialog v-model="savePresetDialogVisible" title="保存为预设" width="500px">
        <el-form label-width="100px">
            <el-form-item label="预设名称">
                <el-input v-model="presetName" placeholder="请输入预设名称" @keyup.enter="savePreset" />
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="savePresetDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="savePreset">确定</el-button>
        </template>
    </el-dialog>

    <!-- 从预设加载对话框 -->
    <el-dialog v-model="loadPresetDialogVisible" title="从预设加载" width="500px">
        <div v-loading="loadingPresets">
            <el-form label-width="100px">
                <el-form-item label="选择预设">
                    <el-select v-model="selectedPresetId" placeholder="请选择预设" style="width: 100%">
                        <el-option v-for="preset in presetList" :key="preset.id" :label="preset.preset_name"
                            :value="preset.id" />
                    </el-select>
                </el-form-item>
            </el-form>
        </div>
        <template #footer>
            <el-button @click="loadPresetDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="loadPreset" :disabled="!selectedPresetId">确定</el-button>
        </template>
    </el-dialog>

    <!-- 预设管理对话框 -->
    <el-dialog v-model="presetManagementVisible" title="预设管理" width="800px" @opened="refreshPresetManagementList">
        <div style="display: flex; flex-direction: column; height: 100%;">
            <!-- 工具栏 -->
            <div style="margin-bottom: 16px;">
                <el-button type="primary" @click="openLoadShareCodeDialog">
                    载入分享预设代码
                </el-button>
            </div>
            <!-- 预设列表表格 -->
            <div v-loading="loadingPresetManagement">
                <el-table :data="presetManagementList" style="width: 100%">
                    <el-table-column label="预设名称" prop="preset_name" min-width="200">
                        <template #default="{ row }">
                            <div v-if="editingPresetId === row.id"
                                style="display: flex; align-items: center; gap: 8px;">
                                <el-input v-model="editingPresetName" :maxlength="20" @blur="savePresetName(row.id)"
                                    @keyup="(e: KeyboardEvent) => handlePresetNameKeyup(e, row.id)" style="flex: 1;"
                                    autofocus />
                                <el-button size="small" type="primary" @click="savePresetName(row.id)">保存</el-button>
                                <el-button size="small" @click="cancelEditPresetName">取消</el-button>
                            </div>
                            <div v-else style="display: flex; align-items: center; gap: 8px;">
                                <span>{{ row.preset_name }}</span>
                                <el-button size="small" type="primary" plain :icon="Edit" circle
                                    @click="startEditPresetName(row)" />
                            </div>
                        </template>
                    </el-table-column>
                    <el-table-column label="操作" width="240" fixed="right">
                        <template #default="{ row }">
                            <el-button size="small" type="primary" plain :icon="Share" @click="sharePreset(row.id)">
                                分享
                            </el-button>
                            <el-button size="small" type="primary" plain :icon="Edit"
                                @click="openEditPresetDialog(row.id)">
                                编辑
                            </el-button>
                            <el-button size="small" type="danger" plain :icon="Delete"
                                @click="deletePreset(row.id, row.preset_name)">
                                删除
                            </el-button>
                        </template>
                    </el-table-column>
                </el-table>
            </div>
        </div>
    </el-dialog>

    <!-- 载入分享预设代码对话框 -->
    <el-dialog v-model="loadShareCodeDialogVisible" title="载入分享预设代码" width="500px">
        <el-form label-width="120px">
            <el-form-item label="分享代码">
                <el-input v-model="shareCodeInput" type="textarea" :rows="4" placeholder="请输入分享代码" />
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="loadShareCodeDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="loadShareCode">确定</el-button>
        </template>
    </el-dialog>

    <!-- 编辑预设对话框 -->
    <el-dialog v-model="presetEditDialogVisible" title="编辑预设" width="800px" :close-on-click-modal="false">
        <div style="display: flex; flex-direction: column; height: 100%;">
            <!-- 工具栏 -->
            <div style="margin-bottom: 16px; display: flex; gap: 8px;">
                <el-button type="primary" :icon="Document" @click="savePresetConfig">
                    保存当前配置
                </el-button>
                <el-button type="warning" :icon="RefreshLeft" @click="resetPresetEdit">
                    重置修改
                </el-button>
                <el-button type="info" :icon="Sort" @click="sortPresetConfigList">
                    整理配置
                </el-button>
            </div>
            <!-- 配置列表 -->
            <div style="flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column;">
                <VueDraggable v-model="editingPresetConfigList" target="tbody" :animation="150" style="height: 100%;">
                    <industry-plan-config-flow-table :list="editingPresetConfigList" :card-style-mode="cardStyleMode"
                        @modify-config-flow="handleModifyConfigFlow"
                        @delete-config-flow="handleDeleteConfigFromPreset" />
                </VueDraggable>
            </div>
        </div>
    </el-dialog>
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

/* 配置流程容器 */
.industry-plan-config-flow-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
}

/* 图标按钮容器 */
.icon-buttons-container {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 12px;
    padding: 12px 0;
    flex-shrink: 0;
}

/* 确保拖拽容器可以正确使用剩余空间 */
.industry-plan-config-flow-container> :deep(.vue-draggable-plus) {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}
</style>