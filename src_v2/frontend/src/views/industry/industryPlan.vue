<script setup lang="ts">
import KTable from '@/components/k/KTable.vue'
import KTableDensitySwitch from '@/components/k/KTableDensitySwitch.vue'
import { ref, onMounted, onUnmounted, nextTick, computed, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { ArrowRight, QuestionFilled, Close, Setting } from '@element-plus/icons-vue'
import { http } from '@/http'
import { VueDraggable } from 'vue-draggable-plus'
import IndustryPlanPlanTable from './components/industryPlanPlanTable.vue'
import IndustryPlanConfigFlow from './components/industryPlanConfigFlow.vue'
import { useAuthStore } from '@/stores/auth'
import { useEdition } from '@/composables/useEdition'
import { storeToRefs } from 'pinia'
import { useTableDensityStore } from '@/stores/tableDensity'
import { onBeforeRouteLeave } from 'vue-router'

const authStore = useAuthStore()
const { isEnterprise } = useEdition()
// 卡片密度统一走全站表格密度偏好（工业类页面默认紧凑），不再单独存一份
const densityStore = useTableDensityStore()
const { density } = storeToRefs(densityStore)
const cardStyleMode = computed<'normal' | 'compact'>(() => (density.value === 'compact' ? 'compact' : 'normal'))
const haveAlphaRole = computed(() => {
  return authStore.user?.roles.includes('vip_alpha') || false
})
const haveAdminRole = computed(() => {
  return authStore.user?.roles.includes('admin') || false
})
const haveOmegaRole = computed(() => {
  return authStore.user?.roles.includes('vip_omega') || false
})

interface PlanProductTableData {
  "row_id": number,
  "type_id": number,
  "quantity": number,
  "type_name": string,
  "type_name_zh": string
  "type": 'group' | 'product'
  "name": string
  "products": PlanProductTableData[]
  "active"?: boolean
  "note"?: string
}

interface PlanRow {
  row_id: number
  type: 'group' | 'product'
  group_id?: string | null        // product 所属的 group name，null 表示不在组内
  order: number                    // 全局顺序
  // product 属性
  type_id?: number
  quantity?: number
  type_name?: string
  type_name_zh?: string
  active?: boolean                 // product 是否启动
  note?: string                    // 备注
  // group 属性
  name?: string                    // group 名称
}

interface PlanSettings {
  name: string,
  considerate_asset: boolean,
  considerate_running_job: boolean,
  split_to_jobs: boolean,
  full_split: boolean,
  considerate_bp_relation: boolean,
  full_use_bp_cp: boolean,
  calculate_lp_blueprint_cost: boolean,
  work_type: string
}

interface PlanTableData {
  "row_id": number,
  "plan_name": string,
  "user_name": string,
  "plan_settings": PlanSettings,
  "products": PlanProductTableData[],
  "plan_key"?: string,
  "plan_display_name"?: string
}

interface SearchResult {
  type_id: number
  type_name_zh: string
}

interface TypeItem {
  value: string
}

interface AuxiliaryCondition {
  id: number
  searchType: string
  keyword: string
}

const marketRootTree = ref([])
const originalMarketRootTree = ref([]) // 保存原始市场树数据，用于恢复
// 从 localStorage 恢复之前选择的计划
const STORAGE_KEY = 'industry_plan_selected_plan'
const selectedPlan = ref<string | null>(localStorage.getItem(STORAGE_KEY) || null)
const getMarketRootTree = async () => {
  const res = await http.post('/EVE/industry/getMarketTree', {
    node: 'root'
  })
  const data = await res.json()
  if (data.status !== 200) {
    ElMessage.error(data.message || '获取市场树失败')
    return
  }
  marketRootTree.value = data.data
  originalMarketRootTree.value = JSON.parse(JSON.stringify(data.data)) // 深拷贝保存原始数据
}

// 搜索市场类型
const searchMarketTypes = async () => {
  const keyword = searchKeyword.value.trim()

  // 如果关键词为空，恢复显示原始市场树
  if (!keyword) {
    // 如果有原始数据，则恢复；否则重新加载
    if (originalMarketRootTree.value.length > 0) {
      marketRootTree.value = JSON.parse(JSON.stringify(originalMarketRootTree.value))
    } else {
      // 如果原始数据还没有加载，重新获取
      await getMarketRootTree()
    }
    return
  }

  try {
    const res = await http.post('/EVE/industry/searchMarketTypes', {
      keyword: keyword
    })
    const data = await res.json()

    if (data.status === 200) {
      marketRootTree.value = data.data || []
      if (marketRootTree.value.length === 0) {
        ElMessage.info('未找到匹配的结果')
      }
    } else {
      ElMessage.error(data.message || '搜索失败')
    }
  } catch (e) {
    ElMessage.error('搜索失败，请稍后重试')
    console.error('搜索市场类型失败:', e)
  }
}

// 懒加载子节点数据
const loadChildTree = async (row: any, treeNode: any, resolve: (data: any[]) => void) => {
  try {
    const res = await http.post('/EVE/industry/getMarketTree', {
      node: row.market_group_id
    })
    const data = await res.json()
    console.log("loadChildTree", data)
    if (data.status !== 200) {
      ElMessage.error(data.message || '加载子节点失败')
      resolve([])
      return
    }
    // 调用 resolve 返回子节点数据
    resolve(data.data || [])
  } catch (error) {
    console.error('加载子节点失败:', error)
    resolve([])
  }
}

const getPlanTableData = async () => {
  console.log("getPlanTableData")
  const res = await http.post('/EVE/industry/getPlanTableData')
  const data = await res.json()
  if (data.status !== 200) {
    ElMessage.error(data.message || '获取计划列表失败')
    return
  }

  // 如果是管理员模式，为每个计划添加 plan_key 和 plan_display_name
  if (haveAdminRole.value) {
    IndustryPlanTableData.value = data.data.map((plan: PlanTableData) => ({
      ...plan,
      plan_key: `${plan.user_name}:${plan.plan_name}`,
      plan_display_name: `${plan.user_name}:${plan.plan_name}`
    }))
  } else {
    IndustryPlanTableData.value = data.data
  }

  // 如果从 localStorage 恢复了计划，但计划列表中不存在，则清除
  if (selectedPlan.value) {
    let planExists = false
    if (haveAdminRole.value) {
      // 管理员模式：查找 plan_key 匹配的计划
      planExists = IndustryPlanTableData.value.some((item: any) => {
        const planKey = item.plan_key || `${item.user_name}:${item.plan_name}`
        return planKey === selectedPlan.value
      })
    } else {
      // 普通模式：只有 plan_name
      planExists = IndustryPlanTableData.value.some(item => item.plan_name === selectedPlan.value)
    }

    if (!planExists) {
      selectedPlan.value = null
      localStorage.removeItem(STORAGE_KEY)
      currentPlanProducts.value = []
      flatPlanProducts.value = []
      planDirty.value = false
      console.log("selectedPlan not found", selectedPlan.value)
      return
    }

    // 加载计划数据
    let plan: PlanTableData | undefined
    if (haveAdminRole.value) {
      plan = IndustryPlanTableData.value.find((item: any) => {
        const planKey = item.plan_key || `${item.user_name}:${item.plan_name}`
        return planKey === selectedPlan.value
      }) as PlanTableData | undefined
    } else {
      plan = IndustryPlanTableData.value.find(item => item.plan_name == selectedPlan.value)
    }

    if (plan) {
      const flat = flattenProducts(plan.products || [])
      // #region agent log (仅开发环境启用)
      if (import.meta.env.DEV) {
        const apiGroups = (plan.products || []).filter((p: any) => p.type === 'group').map((g: any) => ({ name: g.name, productCount: (g.products || []).length, type_ids: (g.products || []).map((p: any) => p.type_id) }))
        const flatProductCount = flat.filter(r => r.type === 'product').length
        fetch('http://127.0.0.1:7242/ingest/7048bd83-86df-46f6-886b-1c2c54b42b3f', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ location: 'industryPlan.vue:getPlanTableData:afterFetch', message: 'API plan.products and flat', data: { planName: plan.plan_name, apiGroups, flatLen: flat.length, flatProductCount }, timestamp: Date.now(), hypothesisId: 'api' }) }).catch(() => {})
      }
      // #endregion
      flatPlanProducts.value = flat
      planDirty.value = false // 载入即干净态
      currentPlanProducts.value = plan.products || []
      current_plan_settings.value = plan.plan_settings || {
        name: '',
        considerate_asset: false,
        considerate_running_job: false,
        split_to_jobs: false,
        full_split: false,
        considerate_bp_relation: false,
        full_use_bp_cp: false,
        calculate_lp_blueprint_cost: false,
        work_type: 'whole'
      }
      current_plan_settings.value.name = plan.plan_name
    }
  } else {
    currentPlanProducts.value = []
  }
  console.log("currentPlanProducts", currentPlanProducts.value)
}

// 新建计划弹窗相关
const dialogVisible = ref(false)
const planFormRef = ref<FormInstance>()
const planFormRules: FormRules = {
  name: [
    { required: true, message: '计划名称不能为空', trigger: 'blur' },
    { min: 1, message: '计划名称不能为空', trigger: 'blur' }
  ]
}
const planForm = ref({
  name: '',
  considerate_asset: false,
  considerate_running_job: false,
  split_to_jobs: false,
  full_split: false,
  considerate_bp_relation: false,
  full_use_bp_cp: false,
  calculate_lp_blueprint_cost: false,
  work_type: 'whole' // 'whole' 按整体考虑, 'in_order' 按顺序安排工作
})

const openCreatePlanDialog = () => {
  // 重置表单
  planForm.value = {
    name: '',
    considerate_asset: false,
    considerate_running_job: false,
    split_to_jobs: false,
    full_split: false,
    considerate_bp_relation: false,
    full_use_bp_cp: false,
    calculate_lp_blueprint_cost: false,
    work_type: 'whole'
  }
  dialogVisible.value = true
  nextTick(() => {
    planFormRef.value?.resetFields()
  })
}

const handleConfirm = async () => {
  const valid = await planFormRef.value?.validate().catch(() => false)
  if (!valid) return
  const res = await http.post('/EVE/industry/createPlan', {
    name: planForm.value.name,
    considerate_asset: planForm.value.considerate_asset,
    considerate_running_job: planForm.value.considerate_running_job,
    split_to_jobs: planForm.value.split_to_jobs,
    full_split: planForm.value.full_split,
    considerate_bp_relation: planForm.value.considerate_bp_relation,
    work_type: planForm.value.work_type
  })
  const data = await res.json()
  if (data.status !== 200) {
    ElMessage.error(data.message || '创建计划失败')
    return
  }
  ElMessage.success("创建成功")
  await getPlanTableData()
  dialogVisible.value = false
}

const handleCancel = () => {
  dialogVisible.value = false
}

const IndustryPlanTableData = ref<PlanTableData[]>([])
const marketRootTreeRef = ref() // 添加表格引用
// 市场树行：可见的「添加产品」按钮只依赖这两列
interface MarketTreeRow {
  type_id?: number | string
  can_add_plan?: boolean
  [key: string]: unknown
}
// 市场树当前选中行（供「添加产品」按钮判定可用性）
const selectedMarketRow = ref<MarketTreeRow | null>(null)
const resetPlanModify = async () => {
  getPlanTableData()
}

// 添加行点击处理函数
const handleRowClick = (row: any) => {
  if (marketRootTreeRef.value) {
    marketRootTreeRef.value.toggleRowExpansion(row)
  }
}

// 市场树选中行变化（highlight-current-row 配套）
const handleMarketRowCurrentChange = (row: MarketTreeRow | null) => {
  selectedMarketRow.value = row
}

const addPlanDialogVisible = ref(false)
const addPlanDialogForm = ref({
  get_plan_loading: false,
  plan_list: [] as PlanTableData[],

  add_plan_loading: false,

  plan_name: '',
  type_id: '',
  quantity: 1,
  group_name: null as string | null
})
// 右键菜单相关
const contextMenuRow = ref<any>(null)
const contextMenuVisible = ref(false)
const contextMenuStyle = ref({ left: '0px', top: '0px' })

// 添加到自选市场清单相关
interface Market {
  id: number
  tag: string
  product_type_ids: number[]
}
const addToMarketDialogVisible = ref(false)
const marketList = ref<Market[]>([])
const selectedMarketId = ref<number | null>(null)
const addToMarketLoading = ref(false)

const handleRowContextMenu = (row: any, column: any, event: MouseEvent) => {
  // 只处理有 can_add_plan 属性的行
  if (!('can_add_plan' in row)) {
    return
  }

  event.preventDefault()
  event.stopPropagation()

  contextMenuRow.value = row
  contextMenuStyle.value = {
    left: event.clientX + 'px',
    top: event.clientY + 'px'
  }
  contextMenuVisible.value = true

  // 添加点击外部关闭菜单的事件监听（使用 nextTick 确保菜单已渲染）
  nextTick(() => {
    document.addEventListener('click', handleClickOutside, { once: true })
  })
}

// 点击外部关闭菜单
const handleClickOutside = (event: MouseEvent) => {
  // 如果点击的不是菜单本身，则关闭菜单
  const target = event.target as HTMLElement
  if (!target.closest('.context-menu')) {
    contextMenuVisible.value = false
  }
}

const handleAddPlan = (command: string) => {
  console.log("handleAddPlan", command)
  addPlanDialogVisible.value = true
  addPlanDialogForm.value.type_id = command
  addPlanDialogForm.value.group_name = null // 重置组选择

  addPlanDialogForm.value.get_plan_loading = true
  getPlanTableData()
  addPlanDialogForm.value.plan_list = IndustryPlanTableData.value
  addPlanDialogForm.value.get_plan_loading = false
}

// 「添加产品」可见入口：与右键菜单走同一套 handleAddPlan 流程
const isSelectedMarketRowAddable = computed(() => {
  const row = selectedMarketRow.value
  if (!row) return false
  return row.type_id != null && row.can_add_plan === true
})

// 空串表示按钮可用。权限门槛与后端对齐：/EVE/industry/addPlanProduct 只有 @auth_required，
// 不校验 Omega，所以这里不按会员等级禁用（批量添加仍由后端 savePlanProducts 之外的产品规则控制）。
const addProductDisabledReason = computed(() => {
  if (!isSelectedMarketRowAddable.value) return '请先在左侧市场树选择可添加的产品'
  return ''
})

const handleAddPlanFromSelected = () => {
  const row = selectedMarketRow.value
  if (addProductDisabledReason.value || !row || row.type_id == null) return
  // handleAddPlanConfirm 从 contextMenuRow 取产品名，这里复用同一行
  contextMenuRow.value = row
  handleAddPlan(String(row.type_id))
}

// 获取当前选中计划的组列表（用于添加产品弹窗）
const getSelectedPlanForAdd = computed(() => {
  if (!addPlanDialogForm.value.plan_name) return undefined

  let plan: PlanTableData | undefined
  if (haveAdminRole.value) {
    const planKey = addPlanDialogForm.value.plan_name
    plan = IndustryPlanTableData.value.find((item: any) => {
      const key = item.plan_key || `${item.user_name}:${item.plan_name}`
      return key === planKey || item.plan_name === planKey
    }) as PlanTableData | undefined
  } else {
    plan = IndustryPlanTableData.value.find(item => item.plan_name === addPlanDialogForm.value.plan_name)
  }
  return plan
})

// 获取当前选中计划的组列表（用于批量添加弹窗）
const getSelectedPlanForBatchAdd = computed(() => {
  if (!batchAddConfirmForm.value.plan_name) return undefined

  let plan: PlanTableData | undefined
  if (haveAdminRole.value) {
    const planKey = batchAddConfirmForm.value.plan_name
    plan = IndustryPlanTableData.value.find((item: any) => {
      const key = item.plan_key || `${item.user_name}:${item.plan_name}`
      return key === planKey || item.plan_name === planKey
    }) as PlanTableData | undefined
  } else {
    plan = IndustryPlanTableData.value.find(item => item.plan_name === batchAddConfirmForm.value.plan_name)
  }
  return plan
})

const ItemInfoDialogVisible = ref(false)
const ItemInfoDialogLoading = ref(false)
const ItemData = ref({
  type_id: 0,
  type_name: '',
  type_name_zh: '',
  meta: '',
  group: '',
  category: '',
  market_group_list: ''
})
const cancelItemInfoDialog = () => {
  ItemInfoDialogVisible.value = false
}

// 根据 Meta 等级返回对应的CSS类名
const getMetaLevelClass = (meta: string): string => {
  if (!meta) return 'default'
  const metaNum = parseInt(meta)
  if (metaNum >= 4) return 'high'
  if (metaNum >= 2) return 'medium'
  if (metaNum >= 1) return 'low'
  return 'default'
}

// 将市场组字符串分割为数组
const getMarketGroupList = (marketGroupStr: string): string[] => {
  if (!marketGroupStr) return []
  return marketGroupStr.split('-').filter(item => item.trim())
}

// 复制到剪贴板
const copyToClipboard = async (text: string | number, label?: string) => {
  const textStr = String(text || '').trim()
  if (!textStr || textStr === '—' || textStr === '') return

  try {
    await navigator.clipboard.writeText(textStr)
    ElMessage.success({
      message: label ? `已复制 ${label}: ${textStr}` : `已复制: ${textStr}`,
      duration: 2000
    })
  } catch (err) {
    // 降级方案：使用传统方法
    const textArea = document.createElement('textarea')
    textArea.value = textStr
    textArea.style.position = 'fixed'
    textArea.style.left = '-9999px'
    textArea.style.opacity = '0'
    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()
    try {
      const successful = document.execCommand('copy')
      if (successful) {
        ElMessage.success({
          message: label ? `已复制 ${label}: ${textStr}` : `已复制: ${textStr}`,
          duration: 2000
        })
      } else {
        ElMessage.error('复制失败，请手动复制')
      }
    } catch (err) {
      ElMessage.error('复制失败，请手动复制')
    }
    document.body.removeChild(textArea)
  }
}

const handleItemInfo = async () => {
  console.log("handleInfo", contextMenuRow.value)
  ItemInfoDialogVisible.value = true
  ItemInfoDialogLoading.value = true

  const res = await http.post('/EVE/industry/getItemInfo', {
    type_id: contextMenuRow.value.type_id
  })
  const data = await res.json()
  if (data.status !== 200) {
    ItemInfoDialogLoading.value = false
    ItemInfoDialogVisible.value = false
    ElMessage.error(data.message || '获取物品信息失败')
    return
  }

  ItemInfoDialogLoading.value = false
  ItemData.value.type_id = data.data.type_id
  ItemData.value.type_name = data.data.type_name
  ItemData.value.type_name_zh = data.data.type_name_zh
  ItemData.value.meta = data.data.meta
  ItemData.value.group = data.data.group
  ItemData.value.category = data.data.category
  ItemData.value.market_group_list = data.data.market_group_list
}

// 打开添加到自选市场清单对话框
const handleAddToMarket = async () => {
  // 防御性守卫：社区版没有 /enterprise/market 接口，直接拦截，不发请求
  if (!isEnterprise) {
    ElMessage.warning('该功能为企业版专属功能')
    return
  }

  if (!contextMenuRow.value?.type_id) {
    ElMessage.warning('无法获取物品信息')
    return
  }

  addToMarketLoading.value = true
  addToMarketDialogVisible.value = true
  selectedMarketId.value = null

  try {
    const res = await http.get('/enterprise/market/list')
    const data = await res.json()
    if (data.status !== 200) {
      ElMessage.error(data.message || '获取自选市场列表失败')
      addToMarketDialogVisible.value = false
      return
    }
    marketList.value = data.data || []
    if (marketList.value.length === 0) {
      ElMessage.warning('暂无自选市场清单，请先创建')
      addToMarketDialogVisible.value = false
    }
  } catch (e) {
    ElMessage.error('获取自选市场列表失败')
    addToMarketDialogVisible.value = false
  } finally {
    addToMarketLoading.value = false
  }
}

// 确认添加到自选市场清单
const handleAddToMarketConfirm = async () => {
  // 防御性守卫：社区版没有 /enterprise/market/update 接口，直接拦截，不发请求
  if (!isEnterprise) {
    ElMessage.warning('该功能为企业版专属功能')
    return
  }

  if (!selectedMarketId.value) {
    ElMessage.warning('请选择自选市场清单')
    return
  }

  if (!contextMenuRow.value?.type_id) {
    ElMessage.error('无法获取物品信息')
    return
  }

  addToMarketLoading.value = true

  try {
    // 获取当前市场的现有 product_type_ids
    const currentMarket = marketList.value.find(m => m.id === selectedMarketId.value)
    if (!currentMarket) {
      ElMessage.error('找不到选定的自选市场')
      addToMarketLoading.value = false
      return
    }

    // 获取现有的 type_ids 列表
    const existingTypeIds = currentMarket.product_type_ids || []
    const newTypeId = contextMenuRow.value.type_id

    // 检查是否已存在
    if (existingTypeIds.includes(newTypeId)) {
      ElMessage.warning('该物品已存在于自选市场清单中')
      addToMarketLoading.value = false
      return
    }

    // 合并并去重
    const mergedTypeIds = [...existingTypeIds, newTypeId]

    // 检查是否超过限制（根据市场设置的模式决定，这里使用粗略模式的限制2000）
    if (mergedTypeIds.length > 2000) {
      ElMessage.error('添加后物品数量超过2000个，无法添加')
      addToMarketLoading.value = false
      return
    }

    // 调用 API 更新自选市场
    const res = await http.post('/enterprise/market/update', {
      market_id: selectedMarketId.value,
      product_type_ids: mergedTypeIds
    })
    const data = await res.json()

    if (data.status !== 200) {
      ElMessage.error(data.message || '添加到自选市场清单失败')
      addToMarketLoading.value = false
      return
    }

    ElMessage.success('成功添加到自选市场清单')
    addToMarketDialogVisible.value = false
    selectedMarketId.value = null
  } catch (e) {
    ElMessage.error('添加到自选市场清单失败')
  } finally {
    addToMarketLoading.value = false
  }
}

const handleContextMenuSelect = (index: string) => {
  if (index === 'add') {
    if (contextMenuRow.value?.type_id) {
      handleAddPlan(contextMenuRow.value.type_id)
    }
  } else if (index === 'info') {
    if (contextMenuRow.value?.type_id) {
      // 处理信息查看逻辑
      handleItemInfo()
      console.log('查看信息', contextMenuRow.value)
    }
  } else if (index === 'addToMarket') {
    if (contextMenuRow.value?.type_id) {
      handleAddToMarket()
    }
  }
  contextMenuVisible.value = false
}

// 获取当前选中计划的完整信息（包含user_name）
const getSelectedPlanInfo = () => {
  if (!selectedPlan.value) return null

  // 如果是管理员模式，selectedPlan 是 plan_key 格式 "user_name:plan_name"
  if (haveAdminRole.value) {
    // 从 planList 中查找匹配的计划
    const plan = IndustryPlanTableData.value.find((p: any) => {
      const key = p.plan_key || `${p.user_name}:${p.plan_name}`
      return key === selectedPlan.value
    })
    if (plan) {
      return { user_name: plan.user_name, plan_name: plan.plan_name }
    }
    // 如果找不到，尝试直接解析 selectedPlan（向后兼容）
    if (selectedPlan.value.includes(':')) {
      const [user_name, plan_name] = selectedPlan.value.split(':', 2)
      return { user_name, plan_name }
    }
  }

  // 普通模式，只有 plan_name
  const plan = IndustryPlanTableData.value.find(item => item.plan_name === selectedPlan.value)
  return plan ? { user_name: plan.user_name, plan_name: plan.plan_name } : null
}

const handleAddPlanConfirm = async () => {
  addPlanDialogForm.value.add_plan_loading = true
  if (addPlanDialogForm.value.plan_name === '') {
    ElMessage.error("请选择计划")
    addPlanDialogForm.value.add_plan_loading = false
    return
  }

  // 查找计划信息
  let plan: PlanTableData | undefined
  if (haveAdminRole.value) {
    // 管理员模式：addPlanDialogForm.value.plan_name 可能是 plan_key 格式
    const planKey = addPlanDialogForm.value.plan_name
    plan = IndustryPlanTableData.value.find((item: any) => {
      const key = item.plan_key || `${item.user_name}:${item.plan_name}`
      return key === planKey || item.plan_name === planKey
    }) as PlanTableData | undefined
  } else {
    plan = IndustryPlanTableData.value.find(item => item.plan_name === addPlanDialogForm.value.plan_name)
  }

  if (!plan) {
    ElMessage.error("无法找到计划信息")
    addPlanDialogForm.value.add_plan_loading = false
    return
  }

  // 获取当前计划的产品数据（嵌套结构）
  let currentProducts = plan.products || []

  // 从 contextMenuRow 获取产品名称信息（如果有）
  const type_name = contextMenuRow.value?.type_name || contextMenuRow.value?.name || ''
  const type_name_zh = contextMenuRow.value?.type_name_zh || ''

  // 构建新产品项并添加到计划
  const newProduct = {
    type_id: parseInt(addPlanDialogForm.value.type_id),
    quantity: addPlanDialogForm.value.quantity,
    type_name: type_name,
    type_name_zh: type_name_zh
  }

  // 使用辅助函数添加产品
  const updatedProducts = addProductToPlan(currentProducts, newProduct, addPlanDialogForm.value.group_name)

  // 构建请求数据
  const requestData: any = {
    plan_name: plan.plan_name,
    products: updatedProducts
  }
  // 如果是管理员模式且计划属于其他用户，传递 user_name
  if (haveAdminRole.value && plan.user_name !== authStore.user?.username) {
    requestData.user_name = plan.user_name
  }

  const res = await http.post('/EVE/industry/savePlanProducts', requestData)
  const data = await res.json()
  if (data.status !== 200) {
    ElMessage.error(data.message || '添加产品失败')
    addPlanDialogForm.value.add_plan_loading = false
    return
  }
  ElMessage.success("添加成功")
  addPlanDialogVisible.value = false
  addPlanDialogForm.value.add_plan_loading = false
  // 重置表单
  addPlanDialogForm.value.group_name = null
  await getPlanTableData()
}

const handle_update_current_plan_products = (newList: PlanRow[]) => {
  console.log("handle_update_current_plan_products", newList)
  flatPlanProducts.value = newList
  planDirty.value = true // 子组件推送 = 有本地改动
  // 同步更新嵌套结构（用于保存）
  currentPlanProducts.value = nestProducts(newList)
  console.log("flatPlanProducts", flatPlanProducts.value)
  console.log("currentPlanProducts", currentPlanProducts.value)
  nextTick()
}

// 获取计划的组列表
const getPlanGroups = (plan: PlanTableData | undefined): Array<{ name: string }> => {
  if (!plan || !plan.products) return []
  return plan.products
    .filter(item => item.type === 'group')
    .map(item => ({ name: item.name || '' }))
    .filter(item => item.name) // 过滤空名称
}

// 添加产品到计划
const addProductToPlan = (
  products: PlanProductTableData[],
  newProduct: { type_id: number, quantity: number, type_name?: string, type_name_zh?: string },
  groupName: string | null
): PlanProductTableData[] => {
  const productItem: PlanProductTableData = {
    row_id: 0, // 后端会生成
    type: 'product',
    type_id: newProduct.type_id,
    quantity: newProduct.quantity,
    type_name: newProduct.type_name || '',
    type_name_zh: newProduct.type_name_zh || '',
    name: '',
    products: []
  }

  if (groupName) {
    // 找到组并添加到组内
    const group = products.find(item => item.type === 'group' && item.name === groupName)
    if (group && group.products) {
      group.products.push(productItem)
    } else {
      // 组不存在，作为独立产品添加
      products.push(productItem)
    }
  } else {
    // 作为独立产品添加到计划末尾
    products.push(productItem)
  }

  return products
}

const currentPlanProducts = ref<PlanProductTableData[]>([])
// 扁平化的产品列表（用于拖拽）
const flatPlanProducts = ref<PlanRow[]>([])
// 计划是否有未保存的本地改动（载入/保存/重置后清零）
const planDirty = ref(false)

// 数据转换：嵌套 → 扁平化
function flattenProducts(nested: PlanProductTableData[]): PlanRow[] {
  const flat: PlanRow[] = []
  let order = 0

  for (const item of nested) {
    if (item.type === 'group') {
      flat.push({
        row_id: item.row_id,
        type: 'group',
        name: item.name,
        order: order++,
        group_id: null
      })

      // 添加组内产品
      if (item.products) {
        for (const product of item.products) {
          flat.push({
            row_id: product.row_id,
            type: 'product',
            type_id: product.type_id,
            quantity: product.quantity,
            type_name: product.type_name,
            type_name_zh: product.type_name_zh,
            group_id: item.name,
            order: order++,
            active: product.active !== undefined ? product.active : true,
            note: product.note
          })
        }
      }
    } else {
      flat.push({
        row_id: item.row_id,
        type: 'product',
        type_id: item.type_id,
        quantity: item.quantity,
        type_name: item.type_name,
        type_name_zh: item.type_name_zh,
        group_id: null,
        order: order++,
        active: item.active !== undefined ? item.active : true,
        note: item.note
      })
    }
  }

  return flat
}

// 数据转换：扁平化 → 嵌套
function nestProducts(flat: PlanRow[]): PlanProductTableData[] {
  const nested: PlanProductTableData[] = []
  const validGroupNames = new Set<string>()
  const groupedProducts = new Map<string, PlanProductTableData[]>()
  const seenProductRowIds = new Map<number, number>()

  const toProductItem = (row: PlanRow): PlanProductTableData => ({
    row_id: row.row_id,
    type: 'product',
    type_id: row.type_id || 0,
    quantity: row.quantity || 0,
    type_name: row.type_name || '',
    type_name_zh: row.type_name_zh || '',
    name: '',
    products: [],
    active: row.active !== undefined ? row.active : true,
    note: row.note
  })

  // 先收集有效分组名称
  for (const row of flat) {
    if (row.type === 'group' && row.name) {
      validGroupNames.add(row.name)
    }
  }

  // 记录 row_id>0 产品最后一次出现位置，避免同一产品在瞬时重排中被重复保存
  for (let i = 0; i < flat.length; i++) {
    const row = flat[i]
    if (row.type === 'product' && row.row_id > 0) {
      seenProductRowIds.set(row.row_id, i)
    }
  }

  // 按 group_id 收集组内产品（与组行先后顺序无关）
  // 防御：仅处理 type==='product' 的行，防止分组被误拖入产品列表后损坏数据结构
  for (let i = 0; i < flat.length; i++) {
    const row = flat[i]
    if (row.type !== 'product') continue
    if (row.row_id > 0 && seenProductRowIds.get(row.row_id) !== i) continue
    // 二次防御：确保 group_id 有效且分组名确实存在
    if (row.group_id == null || !validGroupNames.has(row.group_id)) continue

    const list = groupedProducts.get(row.group_id) || []
    list.push(toProductItem(row))
    groupedProducts.set(row.group_id, list)
  }

  // 组与独立产品仍按扁平顺序输出，保证显示顺序稳定
  for (let i = 0; i < flat.length; i++) {
    const row = flat[i]

    if (row.type === 'group') {
      const groupName = row.name || ''
      nested.push({
        row_id: row.row_id,
        type: 'group',
        name: groupName,
        type_id: 0,
        quantity: 0,
        type_name: '',
        type_name_zh: '',
        products: groupedProducts.get(groupName) || []
      })
      continue
    }

    if (row.type !== 'product') continue
    if (row.row_id > 0 && seenProductRowIds.get(row.row_id) !== i) continue

    // group_id 无效时按独立产品保存
    if (row.group_id == null || !validGroupNames.has(row.group_id)) {
      nested.push(toProductItem(row))
    }
  }

  return nested
}

// 卡片样式模式由全站表格密度偏好推导（见文件顶部 cardStyleMode），
// 旧版本单独存 industry_plan_card_style_mode 的开关已删除，避免两套偏好互相打架。

const handlePlanChange = (value: string) => {
  console.log("handlePlanChange", value)
  selectedPlan.value = value
  // 保存选择的计划到 localStorage
  if (value) {
    localStorage.setItem(STORAGE_KEY, value)
  } else {
    localStorage.removeItem(STORAGE_KEY)
  }

  // 查找计划数据
  let plan: PlanTableData | undefined
  if (haveAdminRole.value) {
    // 管理员模式：使用 plan_key 查找
    plan = IndustryPlanTableData.value.find((item: any) => {
      const planKey = item.plan_key || `${item.user_name}:${item.plan_name}`
      return planKey === value
    }) as PlanTableData | undefined
  } else {
    // 普通模式：使用 plan_name 查找
    plan = IndustryPlanTableData.value.find(item => item.plan_name == value)
  }

  if (plan) {
    // 将嵌套结构转换为扁平结构
    flatPlanProducts.value = flattenProducts(plan.products || [])
    // 保留嵌套结构用于保存
    currentPlanProducts.value = plan.products || []
    current_plan_settings.value = plan.plan_settings || {
      name: '',
      considerate_asset: false,
      considerate_running_job: false,
      split_to_jobs: false,
      full_split: false,
      considerate_bp_relation: false,
      full_use_bp_cp: false,
      calculate_lp_blueprint_cost: false,
      work_type: 'whole'
    }
    current_plan_settings.value.name = plan.plan_name
  } else {
    flatPlanProducts.value = []
    currentPlanProducts.value = []
  }
  planDirty.value = false // 切换计划 = 载入
  console.log("current_plan_settings", current_plan_settings.value)

}

const saveCurrentPlan = async () => {
  const planInfo = getSelectedPlanInfo()
  if (!planInfo) {
    ElMessage.error("无法获取计划信息")
    return
  }

  // 将扁平结构转换为嵌套结构用于保存
  const nestedProducts = nestProducts(flatPlanProducts.value)
  // #region agent log (仅开发环境启用)
  if (import.meta.env.DEV) {
    const groupSummary = nestedProducts.filter((p: any) => p.type === 'group').map((g: any) => ({ name: g.name, productCount: (g.products || []).length, type_ids: (g.products || []).map((p: any) => p.type_id) }))
    fetch('http://127.0.0.1:7242/ingest/7048bd83-86df-46f6-886b-1c2c54b42b3f', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ location: 'industryPlan.vue:saveCurrentPlan:beforeSend', message: 'nestedProducts to send', data: { groupSummary, flatLen: flatPlanProducts.value.length }, timestamp: Date.now(), hypothesisId: 'send' }) }).catch(() => {})
  }
  // #endregion

  const requestData: any = {
    plan_name: planInfo.plan_name,
    products: nestedProducts
  }
  // 如果是管理员模式且计划属于其他用户，传递 user_name
  if (haveAdminRole.value && planInfo.user_name !== authStore.user?.username) {
    requestData.user_name = planInfo.user_name
  }

  const res = await http.post('/EVE/industry/savePlanProducts', requestData)
  const data = await res.json()
  if (data.status !== 200) {
    ElMessage.error(data.message || '保存产品失败')
    return
  }
  ElMessage.success("保存成功")
  planDirty.value = false // 已落库
  getPlanTableData()
}

// 修改计划
const current_plan_settings = ref<PlanSettings>({
  name: '',
  considerate_asset: false,
  considerate_running_job: false,
  split_to_jobs: false,
  full_split: false,
  considerate_bp_relation: false,
  full_use_bp_cp: false,
  calculate_lp_blueprint_cost: false,
  work_type: 'whole'
})
const modifyPlanDialogVisible = ref(false)
const openModifyPlanDialog = () => {
  modifyPlanDialogVisible.value = true
}
const cancelModifyPlan = () => {
  modifyPlanDialogVisible.value = false
}

const modifyPlanForm = ref({
  name: '',
  considerate_asset: false,
  considerate_running_job: false,
  split_to_jobs: false,
  considerate_bp_relation: false,
  work_type: 'whole'
})
const handleConfirmModifyPlan = async () => {
  const planInfo = getSelectedPlanInfo()
  if (!planInfo) {
    ElMessage.error("无法获取计划信息")
    return
  }

  const requestData: any = {
    plan_name: planInfo.plan_name,
    plan_settings: current_plan_settings.value
  }
  // 如果是管理员模式且计划属于其他用户，传递 user_name
  if (haveAdminRole.value && planInfo.user_name !== authStore.user?.username) {
    requestData.user_name = planInfo.user_name
  }

  const res = await http.post('/EVE/industry/modifyPlanSettings', requestData)
  const data = await res.json()
  if (data.status !== 200) {
    ElMessage.error(data.message || '修改计划设置失败')
    return
  }
  ElMessage.success("修改成功")
  modifyPlanDialogVisible.value = false
  getPlanTableData()
}

// 批量添加相关
const batchAddDialogVisible = ref(false)
const batchAddConfirmDialogVisible = ref(false)
const searchType = ref('group')
const searchKeyword = ref('')
const searchResults = ref<SearchResult[]>([])
const selectedSearchResults = ref<SearchResult[]>([])
const searchResultsTableRef = ref()
const auxiliaryConditions = ref<AuxiliaryCondition[]>([])
let auxiliaryConditionIdCounter = 0
const searchLoading = ref(false)
const batchAddConfirmForm = ref({
  plan_name: '',
  quantity: 1,
  get_plan_loading: false,
  group_name: null as string | null
})
const searchTypeOptions = [
  { value: 'typename', label: '物品名称' },
  { value: 'group', label: '物品组' },
  { value: 'meta', label: 'meta等级' },
  { value: 'marketGroup', label: '市场组' },
  { value: 'category', label: '类别' }
]

// 打开批量添加搜索弹窗
const openBatchAddDialog = () => {
  searchType.value = 'group'
  searchKeyword.value = ''
  searchResults.value = []
  auxiliaryConditions.value = []
  batchAddDialogVisible.value = true
}

// 添加辅助条件组
const addAuxiliaryGroup = () => {
  auxiliaryConditions.value.push({
    id: ++auxiliaryConditionIdCounter,
    searchType: 'group',
    keyword: ''
  })
}

// 删除辅助条件组
const removeAuxiliaryGroup = (id: number) => {
  const index = auxiliaryConditions.value.findIndex(item => item.id === id)
  if (index !== -1) {
    auxiliaryConditions.value.splice(index, 1)
  }
}

// 获取辅助条件的自动补全建议
const fetchAuxiliarySuggestions = async (queryString: string, condition: AuxiliaryCondition, cb: (suggestions: TypeItem[]) => void): Promise<void> => {
  if (condition.searchType === 'typename') {
    // typename类型使用getTypeSuggestionsList API
    try {
      const res = await http.post('/EVE/industry/getTypeSuggestionsList', {
        type_name: queryString
      })
      const data = await res.json()
      const results = queryString ? (data.data || []).map((item: any) => ({ value: item.value || item.label || item })) : []
      cb(results)
    } catch (e) {
      cb([])
    }
  } else {
    // 其他类型使用getGroupSuggestions API
    try {
      const res = await http.post('/EVE/industry/getGroupSuggestions', {
        assign_type: condition.searchType,
        query: queryString
      })
      const data = await res.json()
      const results = queryString ? (data.data || []).map((item: any) => ({ value: item.value || item.label || item })) : []
      cb(results)
    } catch (e) {
      cb([])
    }
  }
}

// 为辅助条件创建类型化的获取建议函数
const createAuxiliarySuggestionsFetcher = (condition: AuxiliaryCondition) => {
  return (queryString: string, cb: (suggestions: TypeItem[]) => void) => {
    fetchAuxiliarySuggestions(queryString, condition, cb)
  }
}

// 获取自动补全建议
const fetchSearchSuggestions = async (queryString: string, cb: (suggestions: TypeItem[]) => void) => {
  if (searchType.value === 'typename') {
    // typename类型使用getTypeSuggestionsList API
    try {
      const res = await http.post('/EVE/industry/getTypeSuggestionsList', {
        type_name: queryString
      })
      const data = await res.json()
      const results = queryString ? (data.data || []).map((item: any) => ({ value: item.value || item.label || item })) : []
      cb(results)
    } catch (e) {
      cb([])
    }
  } else {
    // 其他类型使用getGroupSuggestions API
    try {
      const res = await http.post('/EVE/industry/getGroupSuggestions', {
        assign_type: searchType.value,
        query: queryString
      })
      const data = await res.json()
      const results = queryString ? (data.data || []).map((item: any) => ({ value: item.value || item.label || item })) : []
      cb(results)
    } catch (e) {
      cb([])
    }
  }
}

// 执行搜索
const handleBatchSearch = async () => {
  // 防御性守卫：社区版没有 /enterprise/market/search 接口，直接拦截，不发请求
  if (!isEnterprise) {
    ElMessage.warning('批量搜索为企业版专属功能')
    return
  }

  if (!searchKeyword.value.trim()) {
    ElMessage.warning('请输入搜索关键字')
    return
  }

  searchLoading.value = true
  try {
    // 新搜索前清空选中状态
    selectedSearchResults.value = []
    if (searchResultsTableRef.value) {
      searchResultsTableRef.value.clearSelection()
    }

    // 构建辅助条件数组，过滤掉空的关键字
    const auxiliaryConditionsData = auxiliaryConditions.value
      .filter(condition => condition.keyword.trim())
      .map(condition => ({
        search_type: condition.searchType,
        keyword: condition.keyword.trim()
      }))

    const res = await http.post('/enterprise/market/search', {
      search_type: searchType.value,
      keyword: searchKeyword.value.trim(),
      auxiliary_conditions: auxiliaryConditionsData,
      have_bp_only: true
    })
    const data = await res.json()

    if (data.status === 400 && data.count >= 2000) {
      ElMessage.warning(data.message || '匹配结果超过2000个，请缩小搜索范围')
      searchResults.value = data.data || []
    } else if (data.status === 200) {
      searchResults.value = data.data || []
      if (searchResults.value.length === 0) {
        ElMessage.info('未找到匹配的结果')
      }
    } else {
      ElMessage.error(data.message || '搜索失败')
      searchResults.value = []
    }
  } catch (e) {
    ElMessage.error('搜索失败')
    searchResults.value = []
  } finally {
    searchLoading.value = false
  }
}

// 处理搜索结果表格选中变化
const handleSearchSelectionChange = (selection: SearchResult[]) => {
  selectedSearchResults.value = selection
}

// 全选搜索结果
const selectAllSearchResults = () => {
  if (!searchResults.value.length || !searchResultsTableRef.value) return
  searchResultsTableRef.value.clearSelection()
  searchResults.value.forEach(row => {
    searchResultsTableRef.value.toggleRowSelection(row, true)
  })
}

// 全不选搜索结果
const clearAllSearchResults = () => {
  selectedSearchResults.value = []
  if (searchResultsTableRef.value) {
    searchResultsTableRef.value.clearSelection()
  }
}

// 关闭批量搜索弹窗时清理选中状态
const handleBatchAddDialogClose = () => {
  selectedSearchResults.value = []
  if (searchResultsTableRef.value) {
    searchResultsTableRef.value.clearSelection()
  }
}

// 打开批量添加确认弹窗
const openBatchAddConfirmDialog = () => {
  if (selectedSearchResults.value.length === 0) {
    ElMessage.warning('请先选择至少一个物品')
    return
  }
  batchAddConfirmForm.value.plan_name = ''
  batchAddConfirmForm.value.quantity = 1
  batchAddConfirmForm.value.group_name = null // 重置组选择
  batchAddConfirmForm.value.get_plan_loading = true
  getPlanTableData()
  batchAddConfirmForm.value.get_plan_loading = false
  batchAddConfirmDialogVisible.value = true
}

// 确认批量添加
const handleBatchAddConfirm = async () => {
  if (batchAddConfirmForm.value.plan_name === '') {
    ElMessage.error("请选择计划")
    return
  }

  if (batchAddConfirmForm.value.quantity <= 0) {
    ElMessage.error("数量必须大于0")
    return
  }

  // 查找计划信息
  let plan: PlanTableData | undefined
  if (haveAdminRole.value) {
    // 管理员模式：batchAddConfirmForm.value.plan_name 可能是 plan_key 格式
    const planKey = batchAddConfirmForm.value.plan_name
    plan = IndustryPlanTableData.value.find((item: any) => {
      const key = item.plan_key || `${item.user_name}:${item.plan_name}`
      return key === planKey || item.plan_name === planKey
    }) as PlanTableData | undefined
  } else {
    plan = IndustryPlanTableData.value.find(item => item.plan_name === batchAddConfirmForm.value.plan_name)
  }

  if (!plan) {
    ElMessage.error("无法找到计划信息")
    return
  }

  // 获取当前计划的产品数据（嵌套结构）
  let currentProducts = plan.products || []

  // 批量构建所有新产品项（只处理选中的结果）
  for (const result of selectedSearchResults.value) {
    const newProduct = {
      type_id: result.type_id,
      quantity: batchAddConfirmForm.value.quantity,
      type_name: '', // SearchResult 接口中没有 type_name，只有 type_name_zh
      type_name_zh: result.type_name_zh || ''
    }
    // 使用辅助函数添加产品
    currentProducts = addProductToPlan(currentProducts, newProduct, batchAddConfirmForm.value.group_name)
  }

  // 构建请求数据
  const requestData: any = {
    plan_name: plan.plan_name,
    products: currentProducts
  }
  // 如果是管理员模式且计划属于其他用户，传递 user_name
  if (haveAdminRole.value && plan.user_name !== authStore.user?.username) {
    requestData.user_name = plan.user_name
  }

  try {
    const res = await http.post('/EVE/industry/savePlanProducts', requestData)
    const data = await res.json()
    if (data.status === 200) {
      ElMessage.success(`成功添加 ${selectedSearchResults.value.length} 个产品到计划`)
    } else {
      ElMessage.error(data.message || '批量添加失败')
      return
    }
  } catch (e: any) {
    ElMessage.error(e.message || '批量添加失败')
    return
  }

  batchAddConfirmDialogVisible.value = false
  batchAddDialogVisible.value = false
  searchResults.value = []
  searchKeyword.value = ''
  auxiliaryConditions.value = []
  selectedSearchResults.value = []
  // 重置表单
  batchAddConfirmForm.value.group_name = null
  await getPlanTableData()
}

// 删除计划
const deletePlanDialogVisible = ref(false)
const openDeletePlanDialog = () => {
  if (selectedPlan.value === null || selectedPlan.value === undefined) {
    ElMessage.warning("请先选择要删除的计划")
    return
  }
  deletePlanDialogVisible.value = true
}
const cancelDeletePlan = () => {
  deletePlanDialogVisible.value = false
}

const handleConfirmDeletePlan = async () => {
  const planInfo = getSelectedPlanInfo()
  if (!planInfo) {
    ElMessage.warning("无法获取计划信息")
    return
  }

  try {
    // 使用 ElMessageBox 进行二次确认
    const displayName = haveAdminRole.value
      ? `${planInfo.user_name}:${planInfo.plan_name}`
      : planInfo.plan_name
    await ElMessageBox.confirm(
      `确定要删除计划 "${displayName}" 吗？此操作不可恢复！`,
      '删除计划',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
        dangerouslyUseHTMLString: false
      }
    )

    // 执行删除
    const res = await http.post('/EVE/industry/deletePlan', {
      plan_name: planInfo.plan_name
    })
    const data = await res.json()
    if (data.status !== 200) {
      ElMessage.error(data.message || '删除计划失败')
      return
    }
    ElMessage.success("删除成功")
    deletePlanDialogVisible.value = false

    // 如果删除的是当前选中的计划，清除选中状态
    selectedPlan.value = null
    localStorage.removeItem(STORAGE_KEY)
    currentPlanProducts.value = []
    flatPlanProducts.value = []
    current_plan_settings.value = {
      name: '',
      considerate_asset: false,
      considerate_running_job: false,
      split_to_jobs: false,
      full_split: false,
      considerate_bp_relation: false,
      full_use_bp_cp: false,
      calculate_lp_blueprint_cost: false,
      work_type: 'whole'
    }

    // 刷新计划列表
    await getPlanTableData()
  } catch (error: any) {
    // 用户取消删除
    if (error === 'cancel' || error === 'close') {
      return
    }
    ElMessage.error(error.message || "删除失败")
  }
}

// 添加分组
const addGroup = async () => {
  // 检查是否有选中的计划
  const planInfo = getSelectedPlanInfo()
  if (!planInfo) {
    ElMessage.warning("请先选择一个计划")
    return
  }

  try {
    // 使用 ElMessageBox.prompt 弹出输入框
    const { value: groupName } = await ElMessageBox.prompt(
      '请输入分组名称（最多20个字符）',
      '添加分组',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /^.{1,20}$/,  // 1-20个字符
        inputErrorMessage: '分组名称不能为空，且不能超过20个字符'
      }
    )

    if (!groupName || !groupName.trim()) {
      ElMessage.warning("分组名称不能为空")
      return
    }

    const trimmedName = groupName.trim()

    // 检查长度限制（去除空格后）
    if (trimmedName.length > 20) {
      ElMessage.warning("分组名称不能超过20个字符")
      return
    }

    // 检查分组名称是否已存在（在嵌套结构中检查）
    const existingGroup = currentPlanProducts.value.find(
      item => item.type === 'group' && item.name === trimmedName
    )
    if (existingGroup) {
      ElMessage.warning(`分组 "${trimmedName}" 已存在`)
      return
    }

    // 获取当前的嵌套结构 products
    const currentProducts = [...currentPlanProducts.value]

    // 创建新的分组对象（嵌套结构格式）
    const newGroup: PlanProductTableData = {
      row_id: 0,  // 后端会生成
      type: 'group',
      name: trimmedName,
      type_id: 0,
      quantity: 0,
      type_name: '',
      type_name_zh: '',
      products: []
    }

    // 添加到 products 末尾
    currentProducts.push(newGroup)

    // 准备请求数据
    const requestData: any = {
      plan_name: planInfo.plan_name,
      products: currentProducts
    }
    // 如果是管理员模式且计划属于其他用户，传递 user_name
    if (haveAdminRole.value && planInfo.user_name !== authStore.user?.username) {
      requestData.user_name = planInfo.user_name
    }

    // 向后端请求保存分组
    const res = await http.post('/EVE/industry/savePlanProducts', requestData)
    const data = await res.json()
    if (data.status !== 200) {
      ElMessage.error(data.message || '添加分组失败')
      return
    }

    // 从后端获取最新的计划数据
    await getPlanTableData()

    ElMessage.success(`分组 "${trimmedName}" 添加成功`)
  } catch (error: any) {
    // 用户取消操作时，ElMessageBox.prompt 会抛出错误
    if (error !== 'cancel') {
      console.error('添加分组失败:', error)
      ElMessage.error('添加分组失败')
    }
  }
}

// ============== 可拖拽分割线相关 ==============
const RESIZE_STORAGE_KEYS = {
  leftPanel: 'industry_plan_left_panel_width',
  rightSplit: 'industry_plan_right_split_width'
}

// 左侧面板宽度（百分比）
const getInitialLeftWidth = (): number => {
  const saved = localStorage.getItem(RESIZE_STORAGE_KEYS.leftPanel)
  return saved ? parseFloat(saved) : 30
}
const leftPanelWidth = ref<number>(getInitialLeftWidth())

// 右侧分割宽度（百分比，相对于右侧容器）
const getInitialRightSplit = (): number => {
  const saved = localStorage.getItem(RESIZE_STORAGE_KEYS.rightSplit)
  return saved ? parseFloat(saved) : 50
}
const rightSplitWidth = ref<number>(getInitialRightSplit())

// 拖拽状态
const isResizingLeft = ref(false)
const isResizingRight = ref(false)
const resizeStartX = ref(0)
const resizeStartLeftWidth = ref(0)
const resizeStartRightWidth = ref(0)

// 左侧分割线拖拽
const handleLeftResizeStart = (e: MouseEvent) => {
  isResizingLeft.value = true
  resizeStartX.value = e.clientX
  resizeStartLeftWidth.value = leftPanelWidth.value
  document.addEventListener('mousemove', handleLeftResizeMove)
  document.addEventListener('mouseup', handleLeftResizeEnd)
  e.preventDefault()
}

const handleLeftResizeMove = (e: MouseEvent) => {
  if (!isResizingLeft.value) return

  const container = document.querySelector('.industry-plan-main-container') as HTMLElement
  if (!container) return

  const containerWidth = container.offsetWidth
  const deltaX = e.clientX - resizeStartX.value
  const deltaPercent = (deltaX / containerWidth) * 100

  let newWidth = resizeStartLeftWidth.value + deltaPercent

  // 限制最小和最大宽度
  newWidth = Math.max(15, Math.min(50, newWidth))

  leftPanelWidth.value = newWidth
}

const handleLeftResizeEnd = () => {
  isResizingLeft.value = false
  localStorage.setItem(RESIZE_STORAGE_KEYS.leftPanel, leftPanelWidth.value.toString())
  document.removeEventListener('mousemove', handleLeftResizeMove)
  document.removeEventListener('mouseup', handleLeftResizeEnd)
}

// 右侧分割线拖拽
const handleRightResizeStart = (e: MouseEvent) => {
  isResizingRight.value = true
  resizeStartX.value = e.clientX
  resizeStartRightWidth.value = rightSplitWidth.value
  document.addEventListener('mousemove', handleRightResizeMove)
  document.addEventListener('mouseup', handleRightResizeEnd)
  e.preventDefault()
}

const handleRightResizeMove = (e: MouseEvent) => {
  if (!isResizingRight.value) return

  const rightContainer = document.querySelector('.industry-plan-right-container') as HTMLElement
  if (!rightContainer) return

  const containerWidth = rightContainer.offsetWidth
  const deltaX = e.clientX - resizeStartX.value
  const deltaPercent = (deltaX / containerWidth) * 100

  let newWidth = resizeStartRightWidth.value + deltaPercent

  // 限制最小和最大宽度（相对于右侧容器）
  newWidth = Math.max(30, Math.min(70, newWidth))

  rightSplitWidth.value = newWidth
}

const handleRightResizeEnd = () => {
  isResizingRight.value = false
  localStorage.setItem(RESIZE_STORAGE_KEYS.rightSplit, rightSplitWidth.value.toString())
  document.removeEventListener('mousemove', handleRightResizeMove)
  document.removeEventListener('mouseup', handleRightResizeEnd)
}

// 计算容器高度（统一高度管理）
const containerHeight = computed(() => {
  // 假设顶部导航栏高度约为 60px，可以根据实际情况调整
  return 'calc(94vh - 60px - 60px)'
})

onMounted(() => {
  getMarketRootTree()
  getPlanTableData()
})

// 有未保存改动时，离开页面前确认（vue-router 4：返回 false 阻止导航）
onBeforeRouteLeave(async () => {
  if (!planDirty.value) return true
  try {
    await ElMessageBox.confirm('当前计划有未保存的修改，离开后将丢失。确定离开吗？', '未保存的修改', {
      type: 'warning',
      confirmButtonText: '离开',
      cancelButtonText: '留在本页'
    })
    return true
  } catch {
    // 用户选择留在本页
    return false
  }
})

onUnmounted(() => {
  // 清理事件监听器
  document.removeEventListener('mousemove', handleLeftResizeMove)
  document.removeEventListener('mouseup', handleLeftResizeEnd)
  document.removeEventListener('mousemove', handleRightResizeMove)
  document.removeEventListener('mouseup', handleRightResizeEnd)
})


</script>

<template>
  <div class="industry-plan-main-container" :style="{ height: containerHeight }">
    <div class="industry-plan-layout">
      <!-- 左侧市场树区域 -->
      <div class="market-root-tree-container" :style="{ width: `${leftPanelWidth}%` }">
        <el-scrollbar :height="`calc(${containerHeight} - 2vh)`">
          <KTable ref="marketRootTreeRef" @row-click="handleRowClick" @row-contextmenu="handleRowContextMenu"
            @current-change="handleMarketRowCurrentChange" highlight-current-row
            class="market-root-tree-table" :data="marketRootTree" lazy row-key="row_id" :load="loadChildTree">
            <el-table-column prop="name" label="名称">
              <template #header>
                <el-input v-model="searchKeyword" placeholder="搜索名称" size="small" clearable
                  @keyup.enter="searchMarketTypes" @blur="searchMarketTypes" @clear="searchMarketTypes" />
              </template>
              <template #default="scope">
                <span :style="!('can_add_plan' in scope.row) ? 'color: gray;' : ''">
                  {{ scope.row.name }}
                </span>
              </template>
            </el-table-column>
          </KTable>

          <!-- 右键菜单 -->
          <div v-if="contextMenuVisible" class="context-menu" :style="contextMenuStyle" @click.stop>
            <el-menu @select="handleContextMenuSelect">
              <el-menu-item v-if="contextMenuRow?.can_add_plan === true" index="add">
                添加到计划
              </el-menu-item>
              <el-menu-item v-if="isEnterprise && haveOmegaRole && contextMenuRow?.can_add_plan === true"
                index="addToMarket">
                添加到指定的自选市场清单
              </el-menu-item>
              <el-menu-item index="info">
                信息
              </el-menu-item>
            </el-menu>
          </div>
        </el-scrollbar>
      </div>

      <!-- 左侧分割线 -->
      <div class="resize-handle resize-handle-vertical" @mousedown="handleLeftResizeStart"
        :class="{ 'resizing': isResizingLeft }"></div>

      <!-- 右侧计划管理区域 -->
      <div class="industry-plan-right-container" :style="{ width: `${100 - leftPanelWidth}%` }">
        <div class="industry-plan-right-layout">
          <!-- 产品列表区域 -->
          <div class="industry-plan-table-product-list" :style="{ width: `${rightSplitWidth}%` }">
            <div class="plan-control-panel">
              <div class="plan-select-row">
                <span class="plan-label">当前计划: </span>
                <el-select placeholder="请选择计划" v-model="selectedPlan" class="plan-select"
                  :options="IndustryPlanTableData"
                  :props="haveAdminRole ? { value: 'plan_key', label: 'plan_display_name' } : { value: 'plan_name', label: 'plan_name' }"
                  @change="handlePlanChange" />
              </div>
              <div class="plan-buttons-row">
                <!-- 计划级操作：全部直出，一步可达 -->
                <el-button size="small" type="primary" @click="openCreatePlanDialog">
                  <el-icon><Plus /></el-icon>
                  新建计划
                </el-button>
                <el-button size="small" @click="saveCurrentPlan">
                  保存计划
                </el-button>
                <el-button size="small" @click="resetPlanModify">
                  重置修改
                </el-button>
                <el-button size="small" class="danger-ghost" @click="openDeletePlanDialog">
                  删除计划
                </el-button>
              </div>

              <div class="plan-buttons-row row-secondary">
                <!-- 结构级操作 -->
                <el-button size="small" @click="addGroup">
                  添加分组
                </el-button>
                <!-- 可见的「添加产品」入口：与右键菜单同流程 -->
                <el-tooltip :disabled="!addProductDisabledReason" :content="addProductDisabledReason" placement="top">
                  <span class="add-product-trigger">
                    <el-button size="small" type="primary" plain :disabled="!!addProductDisabledReason"
                      @click="handleAddPlanFromSelected">
                      添加产品
                    </el-button>
                  </span>
                </el-tooltip>
                <el-button v-if="haveOmegaRole" size="small" @click="openBatchAddDialog">
                  批量添加
                </el-button>
                <el-button size="small" @click="openModifyPlanDialog">
                  修改计划设置
                </el-button>

                <!-- 密度走全站偏好：与其它页面共用同一份选择，不再维护局部状态 -->
                <div class="density-switch">
                  <KTableDensitySwitch label="卡片密度" />
                </div>
              </div>
            </div>
            <div class="product-table-wrapper">
              <industry-plan-plan-table :list="flatPlanProducts" :card-style-mode="cardStyleMode"
                @update:list="handle_update_current_plan_products" />
            </div>
          </div>

          <!-- 右侧分割线 -->
          <div class="resize-handle resize-handle-vertical" @mousedown="handleRightResizeStart"
            :class="{ 'resizing': isResizingRight }"></div>

          <!-- 配置流程区域 -->
          <div class="industry-plan-table-config-flow" :style="{ width: `${100 - rightSplitWidth}%` }">
            <industry-plan-config-flow v-if="selectedPlan" :selected-plan="selectedPlan" />
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 添加产品弹窗 -->
  <el-dialog v-model="addPlanDialogVisible" title="添加产品" width="500px" :close-on-click-modal="false">
    <el-form :model="addPlanDialogForm" label-width="140px">
      <el-form-item label="计划名称">
        <el-select v-model="addPlanDialogForm.plan_name" filterable :loading="addPlanDialogForm.get_plan_loading"
          placeholder="请选择计划" @change="addPlanDialogForm.group_name = null">
          <el-option v-for="item in addPlanDialogForm.plan_list"
            :key="haveAdminRole ? (item.plan_key || `${item.user_name}:${item.plan_name}`) : item.plan_name"
            :label="haveAdminRole ? (item.plan_display_name || `${item.user_name}:${item.plan_name}`) : item.plan_name"
            :value="haveAdminRole ? (item.plan_key || `${item.user_name}:${item.plan_name}`) : item.plan_name">
            {{ haveAdminRole ? (item.plan_display_name || `${item.user_name}:${item.plan_name}`) : item.plan_name }}
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="选择组（可选）">
        <el-select v-model="addPlanDialogForm.group_name" placeholder="选择组，或选择'无'作为独立产品" clearable
          :disabled="!addPlanDialogForm.plan_name" style="width: 100%">
          <el-option label="无" :value="null" />
          <el-option v-for="group in getPlanGroups(getSelectedPlanForAdd)" :key="group.name" :label="group.name"
            :value="group.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="数量">
        <el-input-number v-model="addPlanDialogForm.quantity" :min="0" :max="1000000" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="addPlanDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="handleAddPlanConfirm">添加</el-button>
    </template>
  </el-dialog>

  <!-- 物品信息弹窗 -->
  <el-dialog v-model="ItemInfoDialogVisible" :loading="ItemInfoDialogLoading" title="物品信息" width="600px"
    :close-on-click-modal="false" class="item-info-dialog">
    <div class="item-info-container">
      <!-- 物品标题区域 -->
      <div class="item-header">
        <div class="item-title-section">
          <h3 class="item-name-zh copyable"
            @click="copyToClipboard(ItemData.type_name_zh || ItemData.type_name, '中文名称')"
            :title="ItemData.type_name_zh || ItemData.type_name ? '点击复制' : ''">
            {{ ItemData.type_name_zh || ItemData.type_name || '未知物品' }}
          </h3>
          <p class="item-name-en copyable" @click="copyToClipboard(ItemData.type_name, '英文名称')"
            :title="ItemData.type_name ? '点击复制' : ''">
            {{ ItemData.type_name }}
          </p>
        </div>
        <el-tag v-if="ItemData.type_id" type="info" class="item-id-tag copyable"
          @click="copyToClipboard(String(ItemData.type_id), '物品ID')" title="点击复制ID">
          ID: {{ ItemData.type_id }}
        </el-tag>
      </div>

      <!-- 详细信息区域 -->
      <el-descriptions :column="1" border class="item-descriptions"
        :label-style="{ width: '120px', fontWeight: '600', color: '#606266' }" :content-style="{ color: '#303133' }">
        <el-descriptions-item label="物品ID">
          <span class="item-value copyable" @click="copyToClipboard(String(ItemData.type_id), '物品ID')"
            :title="ItemData.type_id ? '点击复制' : ''">
            {{ ItemData.type_id || '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="物品名称">
          <span class="item-value copyable" @click="copyToClipboard(ItemData.type_name, '物品名称')"
            :title="ItemData.type_name ? '点击复制' : ''">
            {{ ItemData.type_name || '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="中文名称">
          <span class="item-value highlight copyable" @click="copyToClipboard(ItemData.type_name_zh, '中文名称')"
            :title="ItemData.type_name_zh ? '点击复制' : ''">
            {{ ItemData.type_name_zh || '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="Meta等级">
          <span v-if="ItemData.meta"
            :class="['meta-level', `meta-level-${getMetaLevelClass(ItemData.meta)}`, 'copyable']"
            @click="copyToClipboard(ItemData.meta, 'Meta等级')" title="点击复制">
            {{ ItemData.meta }}
          </span>
          <span v-else class="item-value">—</span>
        </el-descriptions-item>
        <el-descriptions-item label="物品组">
          <span class="item-value copyable" @click="copyToClipboard(ItemData.group, '物品组')"
            :title="ItemData.group ? '点击复制' : ''">
            {{ ItemData.group || '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="类别">
          <span class="item-value copyable" @click="copyToClipboard(ItemData.category, '类别')"
            :title="ItemData.category ? '点击复制' : ''">
            {{ ItemData.category || '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="市场组">
          <div v-if="ItemData.market_group_list" class="market-group-chain">
            <template v-for="(group, index) in getMarketGroupList(ItemData.market_group_list)" :key="index">
              <span class="market-group-text copyable" @click="copyToClipboard(group, '市场组')" title="点击复制此节点">
                {{ group }}
              </span>
              <el-icon v-if="index < getMarketGroupList(ItemData.market_group_list).length - 1"
                class="market-group-separator">
                <ArrowRight />
              </el-icon>
            </template>
          </div>
          <span v-else class="item-value">—</span>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="cancelItemInfoDialog">关闭</el-button>
      </div>
    </template>
  </el-dialog>

  <!-- 新建计划弹窗 -->
  <el-dialog v-model="dialogVisible" title="新建计划" width="500px" :close-on-click-modal="false">
    <el-form ref="planFormRef" :model="planForm" :rules="planFormRules" label-width="250px" label-position="left">
      <el-form-item label="计划名称" prop="name">
        <el-input v-model="planForm.name" placeholder="请输入计划名称" />
      </el-form-item>

      <el-form-item label="是否考虑库存">
        <el-switch v-model="planForm.considerate_asset" :disabled="!haveAlphaRole" />
      </el-form-item>

      <el-form-item label="是否考虑运行中任务">
        <el-switch v-model="planForm.considerate_running_job" :disabled="!haveAlphaRole" />
      </el-form-item>

      <el-form-item>
        <template #label>
          <span>
            是否按照习惯切分工作流
            <el-tooltip content="比如将200流程反应拆分成4个50流程，开启后会根据配置自动拆分" placement="top">
              <el-icon style="margin-left: 4px; cursor: help;">
                <QuestionFilled />
              </el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-switch v-model="planForm.split_to_jobs" />
      </el-form-item>

      <el-form-item>
        <template #label>
          <span>
            是否严格按照最大数量切分工作流
            <el-tooltip content="比如180流程会切分为3个50流程和1个30流程，打开此选项会强制补齐到4个50流程。" placement="top">
              <el-icon style="margin-left: 4px; cursor: help;">
                <QuestionFilled />
              </el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-switch v-model="planForm.full_split" />
      </el-form-item>

      <el-form-item label="是否考虑库存蓝图">
        <el-switch v-model="planForm.considerate_bp_relation" :disabled="!haveAlphaRole" />
      </el-form-item>

      <el-form-item label="蓝图拷贝完全使用">
        <el-switch v-model="current_plan_settings.full_use_bp_cp" :disabled="!haveAlphaRole" />
      </el-form-item>

      <el-form-item label="计算LP蓝图成本">
        <el-switch v-model="planForm.calculate_lp_blueprint_cost" />
      </el-form-item>

      <el-form-item label="工作安排方式">
        <el-radio-group v-model="planForm.work_type">
           <el-radio value="whole">按整体考虑</el-radio>
           <el-radio value="in_order">按顺序安排工作</el-radio>
         </el-radio-group>
       </el-form-item>
     </el-form>
 
     <template #footer>
       <span class="dialog-footer">
         <el-button @click="handleCancel">取消</el-button>
         <el-button type="primary" @click="handleConfirm">确定</el-button>
      </span>
    </template>
  </el-dialog>

  <!-- 修改计划弹窗 -->
  <el-dialog v-model="modifyPlanDialogVisible" title="修改计划" width="800px" :close-on-click-modal="false">
    <el-form :model="current_plan_settings" label-width="250px" label-position="left">
      <el-form-item label="计划名称">
        <el-input v-model="current_plan_settings.name" placeholder="请输入计划名称" disabled />
      </el-form-item>

      <el-form-item label="是否考虑库存">
        <el-switch v-model="current_plan_settings.considerate_asset" :disabled="!haveAlphaRole" />
      </el-form-item>

      <el-form-item label="是否考虑运行中任务">
        <el-switch v-model="current_plan_settings.considerate_running_job" :disabled="!haveAlphaRole" />
      </el-form-item>

      <el-form-item>
        <template #label>
          <span>
            是否按照习惯切分工作流
            <el-tooltip content="比如将200流程反应拆分成4个50流程，开启后会根据配置自动拆分" placement="top">
              <el-icon style="margin-left: 4px; cursor: help;">
                <QuestionFilled />
              </el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-switch v-model="current_plan_settings.split_to_jobs" />
      </el-form-item>

      <el-form-item label="是否严格按照最大数量切分工作流">
        <template #label>
          <span>
            是否严格按照最大数量切分工作流
            <el-tooltip content="比如180流程会切分为3个50流程和1个30流程，打开此选项会强制补齐到4个50流程。" placement="top">
              <el-icon style="margin-left: 4px; cursor: help;">
                <QuestionFilled />
              </el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-switch v-model="current_plan_settings.full_split" />
      </el-form-item>

      <el-form-item label="是否考虑库存蓝图">
        <el-switch v-model="current_plan_settings.considerate_bp_relation" :disabled="!haveAlphaRole" />
      </el-form-item>

      <el-form-item label="蓝图拷贝完全使用">
        <el-switch v-model="current_plan_settings.full_use_bp_cp" :disabled="!haveAlphaRole" />
      </el-form-item>

      <el-form-item label="计算LP蓝图成本">
        <el-switch v-model="current_plan_settings.calculate_lp_blueprint_cost" />
      </el-form-item>

      <el-form-item label="工作安排方式">
        <template #label>
          <span>
            工作安排方式
            <el-tooltip content="比如产品a需要30流程组件a，产品b需要40流程组件a。假设最大切分数量为50，当按照整体考虑时，会进行合并再切分，变成50流程+20流程，按照顺序考虑时，不会进行合并。"
              placement="top">
              <el-icon style="margin-left: 4px; cursor: help;">
                <QuestionFilled />
              </el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-radio-group v-model="current_plan_settings.work_type">
           <el-radio value="whole">按整体考虑</el-radio>
           <el-radio value="in_order">按顺序安排工作</el-radio>
         </el-radio-group>
       </el-form-item>
     </el-form>
 
     <template #footer>
       <span class="dialog-footer">
         <el-button @click="cancelModifyPlan">取消</el-button>
         <el-button type="primary" @click="handleConfirmModifyPlan">确定</el-button>
      </span>
    </template>
  </el-dialog>

  <!-- 批量添加搜索弹窗 -->
  <el-dialog v-model="batchAddDialogVisible" title="搜索物品" width="800px" :close-on-click-modal="false"
    @close="handleBatchAddDialogClose">
    <el-form :model="{ searchType, searchKeyword }" label-width="120px">
      <el-form-item label="搜索类型">
        <el-select v-model="searchType" placeholder="请选择搜索类型" style="width: 100%">
          <el-option v-for="item in searchTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="搜索关键字">
        <el-autocomplete v-model="searchKeyword" :fetch-suggestions="fetchSearchSuggestions" value-key="value"
          placeholder="请输入搜索关键字" style="width: 100%" @keyup.enter="handleBatchSearch" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleBatchSearch" :loading="searchLoading">搜索</el-button>
        <el-tooltip placement="right" :width="500" :raw-content="true">
          <template #content>
            <div style="line-height: 1.8;">
              <div><strong>蓝图：</strong> 字面意思，针对某一张蓝图进行配置</div>
              <div><strong>市场组：</strong>某个物品在市场树中的坐标链。</div>
              <div style="margin-left: 20px;">以Ishtar举例，他的市场组是：Ships → Cruisers → Advanced Cruisers → Heavy Assault
                Cruisers → Gallente → Ishtar</div>
              <div style="margin-left: 20px;">如果我选择Cruisers进行筛选，会对所有的巡洋舰生效。如果我选择Heavy Assault
                Cruisers进行筛选，会对所有的重型突击巡洋舰生效。</div>
              <div style="margin-left: 20px;">市场组关键词可以对坐标链中出现了关键词的所有物品生效。如果使用Gallente，则会对所有盖伦特的舰船生效。</div>
              <div style="margin-top: 10px;"><strong>meta等级、物品组、类别</strong> 是EVE物品所拥有的三种属性</div>
              <div style="margin-left: 20px;">1. meta一般筛选物品的科技等级如T1 T2,势力，死亡空间等</div>
              <div style="margin-left: 20px;">2. 物品组与类别多种多样，需要使用时随时使用信息功能查询</div>
              <br>
              <div>你可以在一个配置中添加多个关键词，关键词之间的关系是与，即必须同时满足。</div>
              <div>举例：如果我选择meta=Tech II, marketGroup=Ships,则会对所有T2船生效。</div>
              <div style="margin-top: 10px;"><strong>PS:</strong> 计划管理中的市场树，右键任意物品点击信息，即可查看物品的属性。建议多查看几个物品，利于理解筛选机制。
              </div>
            </div>
          </template>
          <el-button type="primary" :icon="Setting"
            style="margin: 10px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4); font-weight: 600;">
            如何使用关键词筛选？
          </el-button>
        </el-tooltip>
      </el-form-item>
    </el-form>

    <!-- 辅助搜索条件区域 -->
    <el-divider content-position="left">辅助搜索条件</el-divider>
    <div class="auxiliary-conditions">
      <el-button type="default" size="small" @click="addAuxiliaryGroup" style="margin-bottom: 15px">
        增加组
      </el-button>

      <div v-for="condition in auxiliaryConditions" :key="condition.id" class="auxiliary-condition-group">
        <div class="auxiliary-condition-header">
          <span class="auxiliary-condition-title">条件组 #{{ condition.id }}</span>
          <el-button type="danger" size="small" :icon="Close" circle @click="removeAuxiliaryGroup(condition.id)"
            title="删除此条件组" />
        </div>
        <el-form :model="condition" label-width="120px" style="margin-top: 10px">
          <el-row :gutter="10">
            <el-col :span="12">
              <el-form-item label="搜索类型">
                <el-select v-model="condition.searchType" placeholder="请选择搜索类型" style="width: 100%">
                  <el-option v-for="item in searchTypeOptions" :key="item.value" :label="item.label"
                    :value="item.value" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="搜索关键字">
                <el-autocomplete v-model="condition.keyword"
                  :fetch-suggestions="createAuxiliarySuggestionsFetcher(condition)" value-key="value"
                  placeholder="请输入搜索关键字" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </div>
    </div>

    <!-- 搜索结果展示 -->
    <div v-if="searchResults.length > 0" class="search-results">
      <div class="results-header">
        <span>找到 {{ searchResults.length }} 个匹配结果</span>
        <div class="results-actions">
          <el-button size="small" type="primary" text @click="selectAllSearchResults">
            全选
          </el-button>
          <el-button size="small" type="default" text @click="clearAllSearchResults">
            全不选
          </el-button>
          <span class="selected-count" v-if="selectedSearchResults.length > 0">
            已选择 {{ selectedSearchResults.length }} 个
          </span>
        </div>
      </div>
      <KTable ref="searchResultsTableRef" :data="searchResults" max-height="400px" stripe border
        @selection-change="handleSearchSelectionChange">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="type_id" label="Type ID" width="120" />
        <el-table-column prop="type_name_zh" label="物品名称" />
      </KTable>
    </div>

    <template #footer>
      <el-button @click="batchAddDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="openBatchAddConfirmDialog" :disabled="selectedSearchResults.length === 0">
        添加
      </el-button>
    </template>
  </el-dialog>

  <!-- 批量添加确认弹窗 -->
  <el-dialog v-model="batchAddConfirmDialogVisible" title="批量添加确认" width="500px" :close-on-click-modal="false">
    <el-form :model="batchAddConfirmForm" label-width="140px">
      <el-form-item label="计划名称">
        <el-select v-model="batchAddConfirmForm.plan_name" filterable :loading="batchAddConfirmForm.get_plan_loading"
          placeholder="请选择计划" style="width: 100%" @change="batchAddConfirmForm.group_name = null">
          <el-option v-for="item in IndustryPlanTableData"
            :key="haveAdminRole ? (item.plan_key || `${item.user_name}:${item.plan_name}`) : item.plan_name"
            :label="haveAdminRole ? (item.plan_display_name || `${item.user_name}:${item.plan_name}`) : item.plan_name"
            :value="haveAdminRole ? (item.plan_key || `${item.user_name}:${item.plan_name}`) : item.plan_name">
            {{ haveAdminRole ? (item.plan_display_name || `${item.user_name}:${item.plan_name}`) : item.plan_name }}
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="选择组（可选）">
        <el-select v-model="batchAddConfirmForm.group_name" placeholder="选择组，或选择'无'作为独立产品" clearable
          :disabled="!batchAddConfirmForm.plan_name" style="width: 100%">
          <el-option label="无" :value="null" />
          <el-option v-for="group in getPlanGroups(getSelectedPlanForBatchAdd)" :key="group.name" :label="group.name"
            :value="group.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="数量">
        <el-input-number v-model="batchAddConfirmForm.quantity" :min="1" :max="1000000" style="width: 100%" />
      </el-form-item>
      <el-form-item>
        <el-alert :title="`将添加 ${searchResults.length} 个产品到计划`" type="info" :closable="false" show-icon />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="batchAddConfirmDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="handleBatchAddConfirm">确认添加</el-button>
    </template>
  </el-dialog>

  <!-- 删除计划弹窗 -->
  <el-dialog v-model="deletePlanDialogVisible" title="删除计划" width="500px" :close-on-click-modal="false">
    <div style="padding: 20px 0;">
      <el-alert v-if="selectedPlan" :title="`确定要删除计划 '${selectedPlan}' 吗？`" type="warning" :closable="false" show-icon>
        <template #default>
          <div style="margin-top: 10px;">
            <p style="margin: 0; color: #e6a23c;">此操作将永久删除计划及其所有相关数据，包括：</p>
            <ul style="margin: 10px 0 0 20px; color: #e6a23c;">
              <li>计划设置</li>
              <li>计划产品列表</li>
              <li>计划配置流</li>
              <li>计划蓝图关系</li>
            </ul>
            <p style="margin: 10px 0 0; color: #e6a23c; font-weight: bold;">此操作不可恢复！</p>
          </div>
        </template>
      </el-alert>
      <el-alert v-else title="请先选择要删除的计划" type="info" :closable="false" show-icon />
    </div>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="cancelDeletePlan">取消</el-button>
        <el-button type="danger" @click="handleConfirmDeletePlan" :disabled="!selectedPlan">
          确定删除
        </el-button>
      </span>
    </template>
  </el-dialog>

  <!-- 添加到自选市场清单弹窗 -->
  <el-dialog v-model="addToMarketDialogVisible" title="添加到自选市场清单" width="500px" :close-on-click-modal="false">
    <el-form :model="{ selectedMarketId }" label-width="140px">
      <el-form-item label="选择自选市场">
        <el-select v-model="selectedMarketId" filterable :loading="addToMarketLoading" placeholder="请选择自选市场清单"
          style="width: 100%">
          <el-option v-for="market in marketList" :key="market.id" :label="market.tag" :value="market.id">
            {{ market.tag }}
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item v-if="contextMenuRow?.type_name_zh || contextMenuRow?.name">
        <el-alert
          :title="`将添加物品: ${contextMenuRow?.type_name_zh || contextMenuRow?.name || '未知物品'} (ID: ${contextMenuRow?.type_id || '未知'})`"
          type="info" :closable="false" show-icon />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="addToMarketDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="handleAddToMarketConfirm" :loading="addToMarketLoading"
        :disabled="!selectedMarketId">
        确认添加
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 主容器 */
.industry-plan-main-container {
  width: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.industry-plan-layout {
  display: flex;
  flex-direction: row;
  height: 100%;
  width: 100%;
  overflow: hidden;
}

/* 左侧市场树容器 */
.market-root-tree-container {
  background-color: var(--k-color-surface-soft);
  min-width: 200px;
  max-width: 50%;
  padding: 10px;
  border-radius: var(--k-radius-sm);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

/* 右侧主容器 */
.industry-plan-right-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  flex: 1;
  min-width: 0;
}

.industry-plan-right-layout {
  display: flex;
  flex-direction: row;
  height: 100%;
  width: 100%;
  overflow: hidden;
}

/* 产品列表区域 */
.industry-plan-table-product-list {
  background-color: var(--k-color-surface-soft);
  min-width: 300px;
  max-width: 70%;
  padding: 10px;
  border-radius: var(--k-radius-sm);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

/* 计划控制面板 */
.plan-control-panel {
  padding: 10px;
  background-color: var(--k-color-surface);
  border-radius: var(--k-radius-sm);
  margin-bottom: 10px;
  box-shadow: var(--k-shadow-xs);
}

.plan-select-row {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
  gap: 10px;
}

.plan-label {
  font-weight: 500;
  color: var(--k-color-text-secondary);
  white-space: nowrap;
}

.plan-select {
  flex: 1;
  min-width: 0;
}

.plan-buttons-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

/* 两行按「计划级 / 结构级」分组，而不是让 7 个按钮随便折行 */
.plan-buttons-row.row-secondary {
  margin-top: 6px;
}

/* disabled 按钮不触发事件，tooltip 需要包一层可命中的元素 */
.add-product-trigger {
  display: inline-flex;
}

/* 按钮全部直出，靠「分组 + 主次样式」区分，而不是藏进下拉 */
.plan-buttons-row :deep(.el-button) {
  padding: 4px 9px;
}

.plan-buttons-row :deep(.danger-ghost) {
  color: var(--k-color-danger) !important;
}

.plan-buttons-row :deep(.danger-ghost:hover) {
  border-color: color-mix(in srgb, var(--k-color-danger) 52%, var(--k-color-border)) !important;
  background: var(--k-color-danger-soft) !important;
}

/* 密度切换靠右，和左侧的动作按钮分开 */
.density-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.product-table-wrapper {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 配置流程区域 */
.industry-plan-table-config-flow {
  background-color: var(--k-color-surface-soft);
  min-width: 300px;
  max-width: 70%;
  padding: 10px;
  border-radius: var(--k-radius-sm);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: 1;
  min-width: 0;
}

/* 可拖拽分割线 */
.resize-handle {
  /* 分栏拖拽条：跟随主题，深色下不再是刺眼的白条 */
  background-color: var(--k-color-border);
  cursor: col-resize;
  user-select: none;
  flex-shrink: 0;
  position: relative;
  z-index: 10;
  transition: background-color 0.2s;
}

.resize-handle-vertical {
  width: 4px;
  min-width: 4px;
}

.resize-handle:hover {
  background-color: var(--k-color-primary);
}

.resize-handle.resizing {
  background-color: var(--k-color-primary);
}

.resize-handle::before {
  content: '';
  position: absolute;
  top: 0;
  left: -2px;
  right: -2px;
  bottom: 0;
  cursor: col-resize;
}

.context-menu {
  position: fixed;
  z-index: 9999;
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  border-radius: 4px;
  box-shadow: var(--k-shadow-md);
  min-width: 120px;
}

.context-menu .el-menu {
  border: none;
}

/* 物品信息弹窗样式 */
.item-info-dialog :deep(.el-dialog__body) {
  padding: 20px 24px;
}

.item-info-container {
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  padding-bottom: 20px;
  border-bottom: 2px solid var(--k-color-border-subtle);
}

.item-title-section {
  flex: 1;
}

.item-name-zh {
  margin: 0 0 8px 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--k-color-text);
  line-height: 1.4;
}

.item-name-en {
  margin: 0;
  font-size: 14px;
  color: var(--k-color-text-secondary);
  line-height: 1.4;
}

.item-id-tag {
  margin-left: 12px;
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 12px;
}

.item-descriptions {
  margin-top: 8px;
}

.item-descriptions :deep(.el-descriptions__label) {
  background-color: var(--k-color-surface-soft);
  font-weight: 600;
}

.item-descriptions :deep(.el-descriptions__content) {
  background-color: var(--k-color-surface);
}

.item-value {
  font-size: 14px;
  color: var(--k-color-text);
  word-break: break-word;
}

.item-value.highlight {
  color: var(--k-color-primary);
  font-weight: 500;
}

/* 可复制元素样式 */
.copyable {
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  user-select: none;
}

.copyable:hover {
  opacity: 0.8;
  transform: scale(1.02);
}

.copyable:active {
  transform: scale(0.98);
}

.item-name-zh.copyable:hover,
.item-name-en.copyable:hover {
  color: var(--k-color-primary);
  text-decoration: underline;
}

.item-id-tag.copyable:hover {
  background-color: var(--k-color-primary-soft);
  border-color: color-mix(in srgb, var(--k-color-primary) 30%, var(--k-color-surface));
  transform: scale(1.05);
}

.item-value.copyable:hover {
  color: var(--k-color-primary);
  background-color: color-mix(in srgb, var(--k-color-primary) 10%, var(--k-color-surface));
  padding: 2px 4px;
  border-radius: 4px;
  margin: -2px -4px;
}

.meta-level.copyable:hover {
  opacity: 0.9;
  transform: scale(1.05);
  box-shadow: var(--k-shadow-sm);
}

.item-value.market-group {
  color: var(--k-color-text-secondary);
  line-height: 1.6;
}

/* Meta等级样式 */
.meta-level {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
}

.meta-level-high {
  background-color: var(--k-color-danger-soft);
  color: var(--k-color-danger);
  border: 1px solid var(--k-color-danger-soft-border);
}

.meta-level-medium {
  background-color: var(--k-color-warning-soft);
  color: var(--k-color-warning);
  border: 1px solid var(--k-color-warning-soft-border);
}

.meta-level-low {
  background-color: var(--k-color-success-soft);
  color: var(--k-color-success);
  border: 1px solid var(--k-color-success-soft-border);
}

.meta-level-default {
  background-color: var(--k-color-surface-soft);
  color: var(--k-color-text-secondary);
  border: 1px solid var(--k-color-border);
}

/* 市场组链样式 - 面包屑导航风格 */
.market-group-chain {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  line-height: 1.8;
}

.market-group-text {
  display: inline-block;
  padding: 4px 12px;
  background: linear-gradient(135deg, var(--k-color-surface-soft) 0%, var(--k-color-surface-strong) 100%);
  color: var(--k-color-text-secondary);
  border-radius: var(--k-radius-sm);
  font-size: 13px;
  transition: all 0.2s ease;
  border: 1px solid var(--k-color-border);
  box-shadow: var(--k-shadow-xs);
  position: relative;
}

.market-group-text:hover {
  background: linear-gradient(135deg, var(--k-color-surface-strong) 0%, color-mix(in srgb, var(--k-color-border) 70%, var(--k-color-surface)) 100%);
  color: var(--k-color-text);
  border-color: var(--k-color-border);
  transform: translateY(-1px);
  box-shadow: var(--k-shadow-sm);
}

.market-group-text.copyable {
  cursor: pointer;
}

.market-group-text.copyable:hover {
  background: linear-gradient(135deg, var(--k-color-primary) 0%, color-mix(in srgb, var(--k-color-primary) 72%, var(--k-color-shade)) 100%);
  color: var(--k-color-text-inverse);
  border-color: var(--k-color-primary);
  transform: translateY(-2px) scale(1.05);
  box-shadow: 0 4px 8px color-mix(in srgb, var(--k-color-primary) 30%, transparent);
}

.market-group-text.copyable:active {
  transform: translateY(0) scale(1.02);
  box-shadow: 0 2px 4px color-mix(in srgb, var(--k-color-primary) 20%, transparent);
}

.market-group-separator {
  display: inline-flex;
  align-items: center;
  color: var(--k-color-text-tertiary);
  margin: 0 2px;
  font-size: 14px;
  flex-shrink: 0;
}

.market-group-separator svg {
  width: 14px;
  height: 14px;
}

.item-info-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px;
  border-top: 1px solid var(--k-color-border-subtle);
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .plan-buttons-row {
    flex-direction: column;
  }

  .plan-buttons-row .el-button {
    width: 100%;
  }
}

/* 批量添加相关样式 */
.auxiliary-conditions {
  margin-top: 20px;
}

.auxiliary-condition-group {
  margin-bottom: 15px;
  padding: 15px;
  border: 1px solid var(--k-color-border);
  border-radius: 4px;
  background-color: var(--k-color-surface-soft);
  position: relative;
}

.auxiliary-condition-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--k-color-border-subtle);
}

.auxiliary-condition-title {
  font-weight: 500;
  color: var(--k-color-text-secondary);
  font-size: 14px;
}

.search-results {
  margin-top: 20px;
}

.results-header {
  margin-bottom: 10px;
  font-weight: 500;
  color: var(--k-color-text-secondary);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.results-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.selected-count {
  color: var(--k-color-primary);
}

@media (max-width: 768px) {
  .industry-plan-layout {
    flex-direction: column;
  }

  .market-root-tree-container {
    width: 100% !important;
    max-width: 100%;
    height: 200px;
    min-height: 200px;
  }

  .resize-handle-vertical {
    width: 100%;
    height: 4px;
    cursor: row-resize;
    min-width: 0;
  }

  .industry-plan-right-container {
    width: 100% !important;
    flex: 1;
  }

  .industry-plan-right-layout {
    flex-direction: column;
  }

  .industry-plan-table-product-list,
  .industry-plan-table-config-flow {
    width: 100% !important;
    max-width: 100%;
  }

  .plan-control-panel {
    padding: 8px;
  }

  .plan-select-row {
    flex-direction: column;
    align-items: stretch;
  }

  .plan-select {
    width: 100%;
  }
}

/* Theme override
   这一段都是本文件自有容器类：要么取值与 theme.css 的 legacy 覆盖
   （.industry-plan-table-product-list / .industry-plan-table-config-flow /
   .product-table-wrapper）完全一致，要么在同文件里有同权声明写在后面，
   去掉强制优先级不会改变最终取值。 */
.industry-plan-layout,
.industry-plan-table-main,
.industry-plan-table-product-list,
.industry-plan-table-config-flow,
.product-table-wrapper,
.plan-control-panel,
.market-root-tree-container,
.search-results,
.auxiliary-condition-group {
  background: var(--k-color-surface);
  border-color: var(--k-color-border);
  color: var(--k-color-text);
}

.market-root-tree-container,
.industry-plan-table-config-flow {
  position: relative;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--k-color-primary) 24%, var(--k-color-border)) !important;
  border-radius: 12px;
  background:
    radial-gradient(circle at 8% 12%, color-mix(in srgb, var(--k-color-primary) 8%, transparent) 0%, transparent 34%),
    linear-gradient(155deg,
      color-mix(in srgb, var(--k-color-surface) 97%, var(--k-color-surface-soft)) 0%,
      color-mix(in srgb, var(--k-color-primary) 3%, var(--k-color-surface)) 100%) !important;
  box-shadow:
    inset 0 0 0 1px color-mix(in srgb, var(--k-color-primary) 10%, transparent),
    0 8px 24px color-mix(in srgb, var(--k-color-shade) 16%, transparent);
}

.market-root-tree-container::before,
.industry-plan-table-config-flow::before {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  top: 0;
  height: 2px;
  pointer-events: none;
  background: linear-gradient(90deg,
      transparent 0%,
      color-mix(in srgb, var(--k-color-primary) 52%, transparent) 18%,
      color-mix(in srgb, var(--k-color-primary) 22%, transparent) 82%,
      transparent 100%);
  opacity: 0.9;
}

.market-root-tree-container::after,
.industry-plan-table-config-flow::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.55;
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--k-color-primary) 42%, transparent) 0 8px, transparent 8px) left 10px top 10px / 16px 1px no-repeat,
    linear-gradient(180deg, color-mix(in srgb, var(--k-color-primary) 42%, transparent) 0 8px, transparent 8px) left 10px top 10px / 1px 16px no-repeat,
    linear-gradient(270deg, color-mix(in srgb, var(--k-color-primary) 42%, transparent) 0 8px, transparent 8px) right 10px top 10px / 16px 1px no-repeat,
    linear-gradient(180deg, color-mix(in srgb, var(--k-color-primary) 42%, transparent) 0 8px, transparent 8px) right 10px top 10px / 1px 16px no-repeat;
}

.market-root-tree-container:hover,
.industry-plan-table-config-flow:hover {
  border-color: color-mix(in srgb, var(--k-color-primary) 34%, var(--k-color-border)) !important;
  box-shadow:
    inset 0 0 0 1px color-mix(in srgb, var(--k-color-primary) 18%, transparent),
    0 12px 30px color-mix(in srgb, var(--k-color-primary) 12%, transparent);
}

.market-root-tree-table :deep(.el-table tr:hover > td.el-table__cell),
.industry-plan-table-config-flow :deep(.el-table tr:hover > td.el-table__cell) {
  background: linear-gradient(90deg,
      color-mix(in srgb, var(--k-color-primary) 14%, var(--k-color-surface-soft)) 0%,
      color-mix(in srgb, var(--k-color-primary) 6%, var(--k-color-surface)) 100%) !important;
}

.auxiliary-condition-title,
.results-header,
.market-group-separator {
  color: var(--k-color-text-secondary);
}

/* 面包屑胶囊：`.market-group-text` 的渐变底在下面被统一成 surface-soft，
   同文件后写的同权声明即可覆盖，不需要强制优先级。 */
.market-group-text {
  background: var(--k-color-surface-soft);
  border-color: var(--k-color-border);
  color: var(--k-color-text);
}

.market-group-text:hover {
  background: color-mix(in srgb, var(--k-color-primary) 8%, var(--k-color-surface-soft));
}

.splitter {
  background:
    linear-gradient(180deg,
      color-mix(in srgb, var(--k-color-primary) 14%, var(--k-color-border)) 0%,
      color-mix(in srgb, var(--k-color-primary) 28%, var(--k-color-border)) 50%,
      color-mix(in srgb, var(--k-color-primary) 14%, var(--k-color-border)) 100%) !important;
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--k-color-primary) 18%, transparent),
    0 0 8px color-mix(in srgb, var(--k-color-primary) 18%, transparent);
}

.plan-buttons-row :deep(.el-button),
.plan-control-panel :deep(.el-button),
.results-actions :deep(.el-button),
.market-root-tree-container :deep(.el-button) {
  position: relative;
  overflow: hidden;
  border-radius: var(--k-radius-sm);
  border-width: 1px;
  letter-spacing: 0.02em;
  font-weight: 600;
  background: linear-gradient(180deg,
      color-mix(in srgb, var(--k-color-surface) 90%, var(--k-color-surface-soft)) 0%,
      color-mix(in srgb, var(--k-color-surface-soft) 88%, var(--k-color-surface)) 100%) !important;
  border-color: color-mix(in srgb, var(--k-color-primary) 28%, var(--k-color-border)) !important;
  color: var(--k-color-text) !important;
  box-shadow:
    inset 0 0 0 1px color-mix(in srgb, var(--k-color-primary) 14%, transparent),
    0 0 0 1px color-mix(in srgb, var(--k-color-primary) 10%, transparent) !important;
  transition: transform 0.2s ease, box-shadow 0.22s ease, border-color 0.22s ease, background 0.22s ease, color 0.22s ease;
}

.plan-buttons-row :deep(.el-button:hover),
.plan-control-panel :deep(.el-button:hover),
.results-actions :deep(.el-button:hover),
.market-root-tree-container :deep(.el-button:hover) {
  transform: translateY(-1px);
  color: var(--k-color-primary) !important;
  border-color: color-mix(in srgb, var(--k-color-primary) 44%, var(--k-color-border)) !important;
  background: linear-gradient(140deg,
      color-mix(in srgb, var(--k-color-primary) 14%, var(--k-color-surface-soft)) 0%,
      color-mix(in srgb, var(--k-color-primary) 6%, var(--k-color-surface)) 100%) !important;
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--k-color-primary) 34%, var(--k-color-border)),
    0 8px 20px color-mix(in srgb, var(--k-color-primary) 28%, transparent) !important;
}

.industry-plan-main-container :deep(.el-button--primary) {
  color: var(--k-color-text-inverse) !important;
  border-color: color-mix(in srgb, var(--k-color-primary) 65%, var(--k-color-border)) !important;
  background: linear-gradient(135deg,
      color-mix(in srgb, var(--k-color-primary) 80%, var(--k-color-tint)) 0%,
      var(--k-color-primary) 58%,
      color-mix(in srgb, var(--k-color-primary) 78%, var(--k-color-shade)) 100%) !important;
}

.industry-plan-main-container :deep(.el-button--warning) {
  color: var(--k-color-on-warning) !important;
  border-color: color-mix(in srgb, var(--k-color-warning) 62%, var(--k-color-border)) !important;
  background: linear-gradient(135deg,
      color-mix(in srgb, var(--k-color-warning) 82%, var(--k-color-tint)) 0%,
      var(--k-color-warning) 100%) !important;
}

.industry-plan-main-container :deep(.el-button--danger) {
  color: var(--k-color-text-inverse) !important;
  border-color: color-mix(in srgb, var(--k-color-danger) 62%, var(--k-color-border)) !important;
  background: linear-gradient(135deg,
      color-mix(in srgb, var(--k-color-danger) 80%, var(--k-color-tint)) 0%,
      var(--k-color-danger) 100%) !important;
}

.industry-plan-main-container :deep(.el-button.is-text),
.industry-plan-main-container :deep(.el-button--text),
.industry-plan-main-container :deep(.el-button--link) {
  border-color: transparent !important;
  background: transparent !important;
  color: color-mix(in srgb, var(--k-color-primary) 86%, var(--k-color-tint)) !important;
  box-shadow: none !important;
}

.industry-plan-main-container :deep(.el-button.is-circle) {
  border-radius: 999px !important;
}

/* 单选按钮组（卡片密度）：页面里的 radio 不在弹窗内，theme.css 对 radio 的强制优先级
   规则限定 `.el-overlay .el-dialog`，不会命中；其余对手是 EP 基础规则，靠权重即可，
   整组去掉强制优先级。 */
.industry-plan-main-container :deep(.el-radio-button__inner) {
  border-radius: var(--k-radius-sm);
  border-width: 1px;
  letter-spacing: 0.02em;
  font-weight: 600;
  color: var(--k-color-text-secondary);
  background: linear-gradient(180deg,
      color-mix(in srgb, var(--k-color-surface) 90%, var(--k-color-surface-soft)) 0%,
      color-mix(in srgb, var(--k-color-surface-soft) 88%, var(--k-color-surface)) 100%);
  border-color: color-mix(in srgb, var(--k-color-primary) 28%, var(--k-color-border));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--k-color-primary) 14%, transparent);
  transition: transform 0.2s ease, box-shadow 0.22s ease, border-color 0.22s ease, background 0.22s ease, color 0.22s ease;
}

.industry-plan-main-container :deep(.el-radio-button__inner:hover) {
  transform: translateY(-1px);
  color: var(--k-color-primary);
  border-color: color-mix(in srgb, var(--k-color-primary) 44%, var(--k-color-border));
  background: linear-gradient(140deg,
      color-mix(in srgb, var(--k-color-primary) 14%, var(--k-color-surface-soft)) 0%,
      color-mix(in srgb, var(--k-color-primary) 6%, var(--k-color-surface)) 100%);
}

.industry-plan-main-container :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  color: var(--k-color-text-inverse);
  border-color: color-mix(in srgb, var(--k-color-primary) 65%, var(--k-color-border));
  background: linear-gradient(135deg,
      color-mix(in srgb, var(--k-color-primary) 80%, var(--k-color-tint)) 0%,
      var(--k-color-primary) 58%,
      color-mix(in srgb, var(--k-color-primary) 78%, var(--k-color-shade)) 100%);
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--k-color-primary) 34%, transparent),
    0 8px 20px color-mix(in srgb, var(--k-color-primary) 24%, transparent);
}

.industry-plan-main-container :deep(.el-radio-button.is-disabled .el-radio-button__inner) {
  opacity: 0.62;
  color: var(--k-color-text-secondary);
  background: color-mix(in srgb, var(--k-color-surface-soft) 84%, var(--k-color-surface));
  border-color: var(--k-color-border);
  box-shadow: none;
}

/* Meta 等级配色：这几条与上面同名的规则取值完全相同（high/medium/low/default 的
   文字色），只是写在后面；背景/描边也没有同权对手，去掉强制优先级。 */
.meta-level-high,
.meta-level-medium,
.meta-level-low,
.meta-level-default {
  background-color: color-mix(in srgb, var(--k-color-surface-soft) 75%, var(--k-color-surface));
  border-color: var(--k-color-border);
}

.meta-level-high {
  color: var(--k-color-danger);
}

.meta-level-medium {
  color: var(--k-color-warning);
}

.meta-level-low {
  color: var(--k-color-success);
}

.meta-level-default {
  color: var(--k-color-text-secondary);
}

.market-group-text.copyable:hover {
  background: color-mix(in srgb, var(--k-color-primary) 18%, var(--k-color-surface-soft));
  color: var(--k-color-primary);
  border-color: color-mix(in srgb, var(--k-color-primary) 38%, var(--k-color-border));
  box-shadow: var(--k-shadow-sm);
}

/* 弹窗页脚必须保留强制优先级：theme.css 的 `.el-overlay .el-dialog__footer`
   带强制优先级（背景/描边），普通声明压不住。 */
.item-info-dialog :deep(.el-dialog__footer) {
  border-top-color: var(--k-color-border) !important;
  background: var(--k-color-surface) !important;
}

.auxiliary-condition-header {
  border-bottom-color: var(--k-color-border);
}

.selected-count {
  color: var(--k-color-primary);
}

/* 内联 `color: #e6a23c` 必须靠强制优先级才压得住；与 theme.css 中
   `.el-dialog [style*='color: #e6a23c']` 这条同值规则互相冗余，故本条去掉
   强制优先级后仍由 theme.css 保证同样的取色。 */
:deep(.el-dialog [style*='color: #e6a23c']),
:deep(.el-dialog [style*='color:#e6a23c']) {
  color: var(--k-color-warning);
}

/* 控件底色/描边/文字色：这些选择器权重 (0,3,0) 已高于 EP 自身规则 (0,1,0)，
   且 theme.css 只对禁用态输入框有强制优先级，不冲突；
   仅在 input-number 内部（.el-input-number .el-input__wrapper）需要保留高权重即可。 */
.market-root-tree-container :deep(.el-input__wrapper),
.market-root-tree-container :deep(.el-select__wrapper),
.plan-select :deep(.el-select__wrapper),
.plan-control-panel :deep(.el-input__wrapper),
.plan-control-panel :deep(.el-select__wrapper),
.plan-control-panel :deep(.el-input-number .el-input__wrapper),
.plan-control-panel :deep(.el-input-number__decrease),
.plan-control-panel :deep(.el-input-number__increase) {
  background: var(--k-color-surface-soft);
  border-color: var(--k-color-border);
  color: var(--k-color-text);
}

.plan-control-panel :deep(.el-input__inner),
.plan-control-panel :deep(.el-input-number .el-input__inner),
.market-root-tree-container :deep(.el-input__inner) {
  color: var(--k-color-text);
}

.market-root-tree-container :deep(.el-tree),
.market-root-tree-container :deep(.el-tree-node__content),
.market-root-tree-container :deep(.el-tree-node__label),
.market-root-tree-container :deep(.el-table),
.market-root-tree-container :deep(.el-table .cell),
.market-root-tree-container :deep(.el-table td),
.market-root-tree-container :deep(.el-table th) {
  color: var(--k-color-text) !important;
}

.market-root-tree-container :deep(.el-tree-node:focus > .el-tree-node__content),
.market-root-tree-container :deep(.el-tree-node__content:hover),
.market-root-tree-container :deep(.el-table tr:hover > td.el-table__cell) {
  background: color-mix(in srgb, var(--k-color-primary) 8%, var(--k-color-surface-soft)) !important;
}

.market-root-tree-container :deep([style*='color: gray']),
.market-root-tree-container :deep([style*='color:gray']) {
  color: var(--k-color-text-secondary) !important;
}

/* ── P2-C ≤1280 窄屏兜底 ─────────────────────────────────
   只降级布局，不动基础规则：1281+ 一个字都不变。
   min-width 护栏：1200 以下由既有的 1200 块接管按钮竖排，768 以下由既有
   768 块把三栏改成上下布局（那里用 !important 拉满宽度），这里不参与，
   避免与既有断点抢同一个属性。 */
@media (min-width: 769px) and (max-width: 1280px) {

  /* 产品树只是目录：让出 6% 宽度，计划面板与报表区各宽出约 30px。
     宽度本身由行内 style 给到 30%，这里只压上限，不写在行内打架。 */
  .market-root-tree-container {
    max-width: 24%;
  }

  /* 控制面板收紧内边距，把宽度留给工具栏折行判定 */
  .plan-control-panel {
    padding: 8px;
  }

  /* 按钮间距收紧后，「计划级 / 结构级」两组各少折一行 */
  .plan-buttons-row {
    gap: 4px;
  }
}
</style>
