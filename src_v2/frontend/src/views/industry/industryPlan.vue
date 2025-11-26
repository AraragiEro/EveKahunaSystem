<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight } from '@element-plus/icons-vue'
import { http } from '@/http'
import { VueDraggable } from 'vue-draggable-plus'
import IndustryPlanPlanTable from './components/industryPlanPlanTable.vue'
import IndustryPlanConfigFlow from './components/industryPlanConfigFlow.vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const haveAlphaRole = computed(() => {
    return authStore.user?.roles.includes('vip_alpha') || false
})

interface PlanProductTableData {
  "row_id": number,
  "index_id": number,
  "product_type_id": number,
  "quantity": number,
  "type_name": string,
  "type_name_zh": string
}

interface PlanSettings {
  name: string,
  considerate_asset: boolean,
  considerate_running_job: boolean,
  split_to_jobs: boolean,
  considerate_bp_relation: boolean,
  full_use_bp_cp: boolean,
  work_type: string
}

interface PlanTableData {
  "row_id": number,
  "plan_name": string,
  "user_name": string,
  "plan_settings": PlanSettings,
  "products": PlanProductTableData[]
}

const marketRootTree = ref([])
// 从 localStorage 恢复之前选择的计划
const STORAGE_KEY = 'industry_plan_selected_plan'
const selectedPlan = ref<string | null>(localStorage.getItem(STORAGE_KEY) || null)
const getMarketRootTree = async () => {
  const res = await http.post('/EVE/industry/getMarketTree', {
    node: 'root'
  })
  const data = await res.json()
  marketRootTree.value = data.data
}

// 懒加载子节点数据
const loadChildTree = async (row: any, treeNode: any, resolve: (data: any[]) => void) => {
  try {
    const res = await http.post('/EVE/industry/getMarketTree', {
      node: row.market_group_id
    })
    const data = await res.json()
    console.log("loadChildTree", data)
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
  IndustryPlanTableData.value = data.data
  
  // 如果从 localStorage 恢复了计划，但计划列表中不存在，则清除
  if (selectedPlan.value) {
    const planExists = IndustryPlanTableData.value.some(item => item.plan_name === selectedPlan.value)
    if (!planExists) {
      selectedPlan.value = null
      localStorage.removeItem(STORAGE_KEY)
      currentPlanProducts.value = []
      console.log("selectedPlan not found", selectedPlan.value)
      return
    }
    
    // 加载计划数据
    currentPlanProducts.value = IndustryPlanTableData.value.find(item => item.plan_name == selectedPlan.value)?.products || []
    current_plan_settings.value = IndustryPlanTableData.value.find(item => item.plan_name == selectedPlan.value)?.plan_settings || {
      name: '',
      considerate_asset: false,
      considerate_running_job: false,
      split_to_jobs: false,
      considerate_bp_relation: false,
      full_use_bp_cp: false,
      work_type: 'whole'
    }
    current_plan_settings.value.name = selectedPlan.value
  } else {
    currentPlanProducts.value = []
  }
  console.log("currentPlanProducts", currentPlanProducts.value)
}

// 新建计划弹窗相关
const dialogVisible = ref(false)
const planForm = ref({
  name: '',
  considerate_asset: false,
  considerate_running_job: false,
  split_to_jobs: false,
  considerate_bp_relation: false,
  work_type: 'whole' // 'whole' 按整体考虑, 'in_order' 按顺序安排工作
})

const openCreatePlanDialog = () => {
  // 重置表单
  planForm.value = {
    name: '',
    considerate_asset: false,
    considerate_running_job: false,
    split_to_jobs: false,
    considerate_bp_relation: false,
    work_type: 'whole'
  }
  dialogVisible.value = true
}

const handleConfirm = async () => {
  // TODO: 处理确认逻辑，提交表单数据
  const res = await http.post('/EVE/industry/createPlan', {
    name: planForm.value.name,
    considerate_asset: planForm.value.considerate_asset,
    considerate_running_job: planForm.value.considerate_running_job,
    split_to_jobs: planForm.value.split_to_jobs,
    considerate_bp_relation: planForm.value.considerate_bp_relation,
    work_type: planForm.value.work_type
  })
  const data = await res.json()
  const code = res.status
  if (code === 200) {
    ElMessage.success("创建成功")
    await getPlanTableData()
  } else {
    ElMessage.error(data.message)
  }
  dialogVisible.value = false
}

const handleCancel = () => {
  dialogVisible.value = false
}

const IndustryPlanTableData = ref<PlanTableData[]>([])
const marketRootTreeRef = ref() // 添加表格引用
const resetPlanModify = async () => {
  getPlanTableData()
}

// 添加行点击处理函数
const handleRowClick = (row: any) => {
  if (marketRootTreeRef.value) {
    marketRootTreeRef.value.toggleRowExpansion(row)
  }
}

const addPlanDialogVisible = ref(false)
const addPlanDialogForm = ref({
  get_plan_loading: false,
  plan_list: [] as PlanTableData[],

  add_plan_loading: false,
  
  plan_name: '',
  type_id: '',
  quantity: 1
})
// 右键菜单相关
const contextMenuRow = ref<any>(null)
const contextMenuVisible = ref(false)
const contextMenuStyle = ref({ left: '0px', top: '0px' })

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

  addPlanDialogForm.value.get_plan_loading = true
  getPlanTableData()
  addPlanDialogForm.value.plan_list = IndustryPlanTableData.value
  addPlanDialogForm.value.get_plan_loading = false
}

const ItemInfoDialogVisible = ref(false)
const ItemInfoDialogLoading = ref(false)
const ItemData = ref({
  type_id: 0,
  type_name: '',
  type_name_zh: '',
  meta: '',
  group: '',
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
  if (res.status !== 200) {
    ItemInfoDialogLoading.value = false
    ItemInfoDialogVisible.value = false
    ElMessage.error(data.message)
    return
  }
  
  ItemInfoDialogLoading.value = false
  ItemData.value.type_id = data.data.type_id
  ItemData.value.type_name = data.data.type_name
  ItemData.value.type_name_zh = data.data.type_name_zh
  ItemData.value.meta = data.data.meta
  ItemData.value.group = data.data.group
  ItemData.value.market_group_list = data.data.market_group_list
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
  }
  contextMenuVisible.value = false
}

const handleAddPlanConfirm = async () => {
  addPlanDialogForm.value.add_plan_loading = true
  if (addPlanDialogForm.value.plan_name === '') {
    ElMessage.error("请选择计划")
    addPlanDialogForm.value.add_plan_loading = false
    return
  }
  const res = await http.post('/EVE/industry/addPlanProduct', {
    plan_name: addPlanDialogForm.value.plan_name,
    type_id: addPlanDialogForm.value.type_id,
    quantity: addPlanDialogForm.value.quantity
  })
  const data = await res.json()
  const code = res.status
  if (code === 200) {
    ElMessage.success("添加成功")
    addPlanDialogVisible.value = false
    addPlanDialogForm.value.add_plan_loading = false
    getPlanTableData()
  }
}

const currentPlanProducts = ref<PlanProductTableData[]>([])
const handlePlanChange = (value: string) => {
  console.log("handlePlanChange", value)
  selectedPlan.value = value
  // 保存选择的计划到 localStorage
  if (value) {
    localStorage.setItem(STORAGE_KEY, value)
  } else {
    localStorage.removeItem(STORAGE_KEY)
  }
  currentPlanProducts.value = IndustryPlanTableData.value.find(item => item.plan_name == value)?.products || []
  current_plan_settings.value = IndustryPlanTableData.value.find(item => item.plan_name == value)?.plan_settings || {
    name: '',
    considerate_asset: false,
    considerate_running_job: false,
    split_to_jobs: false,
    considerate_bp_relation: false,
    full_use_bp_cp: false,
    work_type: 'whole'
  }
  current_plan_settings.value.name = value
  console.log("current_plan_settings", current_plan_settings.value)
}

const saveCurrentPlan = async () => {
  const res = await http.post('/EVE/industry/savePlanProducts', {
    plan_name: selectedPlan.value,
    products: currentPlanProducts.value
  })
  const data = await res.json()
  const code = res.status
  if (code === 200) {
    ElMessage.success("保存成功")
  } else {
    ElMessage.error(data.message)
  }
  getPlanTableData()
}

// 修改计划
const current_plan_settings = ref<PlanSettings>({
  name: '',
  considerate_asset: false,
  considerate_running_job: false,
  split_to_jobs: false,
  considerate_bp_relation: false,
  full_use_bp_cp: false,
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
  const res = await http.post('/EVE/industry/modifyPlanSettings', {
    plan_name: selectedPlan.value,
    plan_settings: current_plan_settings.value
  })
  const data = await res.json()
  const code = res.status
  if (code === 200) {
    ElMessage.success("修改成功")
    modifyPlanDialogVisible.value = false
    getPlanTableData()
  } else {
    ElMessage.error(data.message)
  }
}

// 删除计划
const deletePlanDialogVisible = ref(false)
const openDeletePlanDialog = () => {
  if (!selectedPlan.value) {
    ElMessage.warning("请先选择要删除的计划")
    return
  }
  deletePlanDialogVisible.value = true
}
const cancelDeletePlan = () => {
  deletePlanDialogVisible.value = false
}

const handleConfirmDeletePlan = async () => {
  if (!selectedPlan.value) {
    ElMessage.warning("请先选择要删除的计划")
    return
  }

  try {
    // 使用 ElMessageBox 进行二次确认
    await ElMessageBox.confirm(
      `确定要删除计划 "${selectedPlan.value}" 吗？此操作不可恢复！`,
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
      plan_name: selectedPlan.value
    })
    const data = await res.json()
    const code = res.status

    if (code === 200) {
      ElMessage.success("删除成功")
      deletePlanDialogVisible.value = false
      
      // 如果删除的是当前选中的计划，清除选中状态
      const deletedPlanName = selectedPlan.value
      selectedPlan.value = null
      localStorage.removeItem(STORAGE_KEY)
      currentPlanProducts.value = []
      current_plan_settings.value = {
        name: '',
        considerate_asset: false,
        considerate_running_job: false,
        split_to_jobs: false,
        considerate_bp_relation: false,
        full_use_bp_cp: false,
        work_type: 'whole'
      }
      
      // 刷新计划列表
      await getPlanTableData()
    } else {
      ElMessage.error(data.message || "删除失败")
    }
  } catch (error: any) {
    // 用户取消删除
    if (error === 'cancel' || error === 'close') {
      return
    }
    ElMessage.error(error.message || "删除失败")
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
      <div 
        class="market-root-tree-container" 
        :style="{ width: `${leftPanelWidth}%` }"
      >
        <el-scrollbar :height="`calc(${containerHeight} - 2vh)`">
          <el-table
            ref="marketRootTreeRef"
            @row-click="handleRowClick"
            @row-contextmenu="handleRowContextMenu"
            class="market-root-tree-table"
            :data="marketRootTree"
            lazy
            row-key="row_id"
            :load="loadChildTree"
          >
            <el-table-column prop="name" label="名称">
              <template #default="scope">
                <span
                  :style="!('can_add_plan' in scope.row) ? 'color: gray;' : ''"
                >
                  {{ scope.row.name }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          
          <!-- 右键菜单 -->
          <div
            v-if="contextMenuVisible"
            class="context-menu"
            :style="contextMenuStyle"
            @click.stop
          >
            <el-menu @select="handleContextMenuSelect">
              <el-menu-item
                v-if="contextMenuRow?.can_add_plan === true"
                index="add"
              >
                添加到计划
              </el-menu-item>
              <el-menu-item index="info">
                信息
              </el-menu-item>
            </el-menu>
          </div>
        </el-scrollbar>
      </div>

      <!-- 左侧分割线 -->
      <div 
        class="resize-handle resize-handle-vertical"
        @mousedown="handleLeftResizeStart"
        :class="{ 'resizing': isResizingLeft }"
      ></div>

      <!-- 右侧计划管理区域 -->
      <div 
        class="industry-plan-right-container"
        :style="{ width: `${100 - leftPanelWidth}%` }"
      >
        <div class="industry-plan-right-layout">
          <!-- 产品列表区域 -->
          <div 
            class="industry-plan-table-product-list"
            :style="{ width: `${rightSplitWidth}%` }"
          >
            <div class="plan-control-panel">
              <div class="plan-select-row">
                <span class="plan-label">当前计划: </span>
                <el-select
                  placeholder="请选择计划"
                  v-model="selectedPlan"
                  class="plan-select"
                  :options="IndustryPlanTableData"
                  :props="{value:'plan_name', label:'plan_name'}"
                  @change="handlePlanChange"
                />
              </div>
              <div class="plan-buttons-row">
                <el-button size="small" @click="saveCurrentPlan">
                  保存计划
                </el-button>
                <el-button size="small" @click="resetPlanModify">
                  重置修改
                </el-button>
                <el-button size="small" @click="openCreatePlanDialog">
                  新建计划
                </el-button>
                <el-button size="small" @click="openDeletePlanDialog">
                  删除计划
                </el-button>
                <el-button size="small" @click="openModifyPlanDialog">
                  修改计划设置
                </el-button>
              </div>
            </div>
            <div class="product-table-wrapper">
              <VueDraggable
                v-model="currentPlanProducts"
                target="tbody"
                :animation="150"
                style="height: 100%;"
              >
                <industry-plan-plan-table :list="currentPlanProducts" />
              </VueDraggable>
            </div>
          </div>

          <!-- 右侧分割线 -->
          <div 
            class="resize-handle resize-handle-vertical"
            @mousedown="handleRightResizeStart"
            :class="{ 'resizing': isResizingRight }"
          ></div>

          <!-- 配置流程区域 -->
          <div 
            class="industry-plan-table-config-flow"
            :style="{ width: `${100 - rightSplitWidth}%` }"
          >
            <industry-plan-config-flow v-if="selectedPlan" :selected-plan="selectedPlan" />
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 添加产品弹窗 -->
  <el-dialog
    v-model="addPlanDialogVisible"
    title="添加产品"
    width="500px"
    :close-on-click-modal="false"
  >
    <el-form :model="addPlanDialogForm" label-width="140px">
      <el-form-item label="计划名称">
        <el-select
          v-model="addPlanDialogForm.plan_name"
          filterable
          :loading="addPlanDialogForm.get_plan_loading"
          placeholder="请选择计划"
        >
          <el-option 
            v-for="item in addPlanDialogForm.plan_list"
            :key="item.plan_name"
            :label="item.plan_name"
            :value="item.plan_name"
          >
            {{ item.plan_name }}
          </el-option>
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
   <el-dialog
    v-model="ItemInfoDialogVisible"
    :loading="ItemInfoDialogLoading"
    title="物品信息"
    width="600px"
    :close-on-click-modal="false"
    class="item-info-dialog"
  >
    <div class="item-info-container">
      <!-- 物品标题区域 -->
      <div class="item-header">
        <div class="item-title-section">
          <h3 
            class="item-name-zh copyable" 
            @click="copyToClipboard(ItemData.type_name_zh || ItemData.type_name, '中文名称')"
            :title="ItemData.type_name_zh || ItemData.type_name ? '点击复制' : ''"
          >
            {{ ItemData.type_name_zh || ItemData.type_name || '未知物品' }}
          </h3>
          <p 
            class="item-name-en copyable" 
            @click="copyToClipboard(ItemData.type_name, '英文名称')"
            :title="ItemData.type_name ? '点击复制' : ''"
          >
            {{ ItemData.type_name }}
          </p>
        </div>
        <el-tag 
          v-if="ItemData.type_id" 
          type="info" 
          class="item-id-tag copyable"
          @click="copyToClipboard(String(ItemData.type_id), '物品ID')"
          title="点击复制ID"
        >
          ID: {{ ItemData.type_id }}
        </el-tag>
      </div>

      <!-- 详细信息区域 -->
      <el-descriptions 
        :column="1" 
        border 
        class="item-descriptions"
        :label-style="{ width: '120px', fontWeight: '600', color: '#606266' }"
        :content-style="{ color: '#303133' }"
      >
        <el-descriptions-item label="物品ID">
          <span 
            class="item-value copyable" 
            @click="copyToClipboard(String(ItemData.type_id), '物品ID')"
            :title="ItemData.type_id ? '点击复制' : ''"
          >
            {{ ItemData.type_id || '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="物品名称">
          <span 
            class="item-value copyable" 
            @click="copyToClipboard(ItemData.type_name, '物品名称')"
            :title="ItemData.type_name ? '点击复制' : ''"
          >
            {{ ItemData.type_name || '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="中文名称">
          <span 
            class="item-value highlight copyable" 
            @click="copyToClipboard(ItemData.type_name_zh, '中文名称')"
            :title="ItemData.type_name_zh ? '点击复制' : ''"
          >
            {{ ItemData.type_name_zh || '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="Meta等级">
          <span 
            v-if="ItemData.meta" 
            :class="['meta-level', `meta-level-${getMetaLevelClass(ItemData.meta)}`, 'copyable']"
            @click="copyToClipboard(ItemData.meta, 'Meta等级')"
            title="点击复制"
          >
            {{ ItemData.meta }}
          </span>
          <span v-else class="item-value">—</span>
        </el-descriptions-item>
        <el-descriptions-item label="物品组">
          <span 
            class="item-value copyable" 
            @click="copyToClipboard(ItemData.group, '物品组')"
            :title="ItemData.group ? '点击复制' : ''"
          >
            {{ ItemData.group || '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="市场组">
          <div v-if="ItemData.market_group_list" class="market-group-chain">
            <template v-for="(group, index) in getMarketGroupList(ItemData.market_group_list)" :key="index">
              <span 
                class="market-group-text copyable" 
                @click="copyToClipboard(group, '市场组')"
                title="点击复制此节点"
              >
                {{ group }}
              </span>
              <el-icon v-if="index < getMarketGroupList(ItemData.market_group_list).length - 1" class="market-group-separator">
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
  <el-dialog
    v-model="dialogVisible"
    title="新建计划"
    width="500px"
    :close-on-click-modal="false"
  >
    <el-form :model="planForm" label-width="140px">
      <el-form-item label="计划名称">
        <el-input v-model="planForm.name" placeholder="请输入计划名称" />
      </el-form-item>
      
      <el-form-item label="是否考虑库存">
        <el-switch v-model="planForm.considerate_asset" :disabled="!haveAlphaRole" />
      </el-form-item>
      
      <el-form-item label="是否考虑运行中任务">
        <el-switch v-model="planForm.considerate_running_job" :disabled="!haveAlphaRole" />
      </el-form-item>
      
      <el-form-item label="是否按照习惯切分工作流">
        <el-switch v-model="planForm.split_to_jobs" />
      </el-form-item>
      
      <el-form-item label="是否考虑库存蓝图">
        <el-switch v-model="planForm.considerate_bp_relation" :disabled="!haveAlphaRole"/>
      </el-form-item>
      
      <el-form-item label="蓝图拷贝完全使用">
        <el-switch v-model="current_plan_settings.full_use_bp_cp" :disabled="!haveAlphaRole" />
      </el-form-item>

      <el-form-item label="工作安排方式">
        <el-radio-group v-model="planForm.work_type">
          <el-radio label="whole">按整体考虑</el-radio>
          <el-radio label="in_order">按顺序安排工作</el-radio>
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
  <el-dialog
    v-model="modifyPlanDialogVisible"
    title="修改计划"
    width="500px"
    :close-on-click-modal="false"
  >
    <el-form :model="current_plan_settings" label-width="140px">
      <el-form-item label="计划名称">
        <el-input v-model="current_plan_settings.name" placeholder="请输入计划名称" disabled/>
      </el-form-item>
      
      <el-form-item label="是否考虑库存">
        <el-switch v-model="current_plan_settings.considerate_asset" :disabled="!haveAlphaRole" />
      </el-form-item>
      
      <el-form-item label="是否考虑运行中任务">
        <el-switch v-model="current_plan_settings.considerate_running_job" :disabled="!haveAlphaRole" />
      </el-form-item>
      
      <el-form-item label="是否按照习惯切分工作流">
        <el-switch v-model="current_plan_settings.split_to_jobs" />
      </el-form-item>
      
      <el-form-item label="是否考虑库存蓝图">
        <el-switch v-model="current_plan_settings.considerate_bp_relation" :disabled="!haveAlphaRole" />
      </el-form-item>

      <el-form-item label="蓝图拷贝完全使用">
        <el-switch v-model="current_plan_settings.full_use_bp_cp" :disabled="!haveAlphaRole" />
      </el-form-item>
      
      <el-form-item label="工作安排方式">
        <el-radio-group v-model="current_plan_settings.work_type">
          <el-radio label="whole">按整体考虑</el-radio>
          <el-radio label="in_order">按顺序安排工作</el-radio>
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

  <!-- 删除计划弹窗 -->
  <el-dialog
    v-model="deletePlanDialogVisible"
    title="删除计划"
    width="500px"
    :close-on-click-modal="false"
  >
    <div style="padding: 20px 0;">
      <el-alert
        v-if="selectedPlan"
        :title="`确定要删除计划 '${selectedPlan}' 吗？`"
        type="warning"
        :closable="false"
        show-icon
      >
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
      <el-alert
        v-else
        title="请先选择要删除的计划"
        type="info"
        :closable="false"
        show-icon
      />
    </div>
    
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="cancelDeletePlan">取消</el-button>
        <el-button 
          type="danger" 
          @click="handleConfirmDeletePlan"
          :disabled="!selectedPlan"
        >
          确定删除
        </el-button>
      </span>
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
  background-color: #f5f7fa;
  min-width: 200px;
  max-width: 50%;
  padding: 10px;
  border-radius: 10px;
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
  background-color: #f5f7fa;
  min-width: 300px;
  max-width: 70%;
  padding: 10px;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

/* 计划控制面板 */
.plan-control-panel {
  padding: 10px;
  background-color: #ffffff;
  border-radius: 8px;
  margin-bottom: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.plan-select-row {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
  gap: 10px;
}

.plan-label {
  font-weight: 500;
  color: #606266;
  white-space: nowrap;
}

.plan-select {
  flex: 1;
  min-width: 0;
}

.plan-buttons-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.product-table-wrapper {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 配置流程区域 */
.industry-plan-table-config-flow {
  background-color: #f5f7fa;
  min-width: 300px;
  max-width: 70%;
  padding: 10px;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: 1;
  min-width: 0;
}

/* 可拖拽分割线 */
.resize-handle {
  background-color: #e4e7ed;
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
  background-color: #409eff;
}

.resize-handle.resizing {
  background-color: #409eff;
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
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
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
  border-bottom: 2px solid #f0f2f5;
}

.item-title-section {
  flex: 1;
}

.item-name-zh {
  margin: 0 0 8px 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  line-height: 1.4;
}

.item-name-en {
  margin: 0;
  font-size: 14px;
  color: #909399;
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
  background-color: #fafafa;
  font-weight: 600;
}

.item-descriptions :deep(.el-descriptions__content) {
  background-color: #ffffff;
}

.item-value {
  font-size: 14px;
  color: #303133;
  word-break: break-word;
}

.item-value.highlight {
  color: #409eff;
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
  color: #409eff;
  text-decoration: underline;
}

.item-id-tag.copyable:hover {
  background-color: #ecf5ff;
  border-color: #b3d8ff;
  transform: scale(1.05);
}

.item-value.copyable:hover {
  color: #409eff;
  background-color: #f0f9ff;
  padding: 2px 4px;
  border-radius: 4px;
  margin: -2px -4px;
}

.meta-level.copyable:hover {
  opacity: 0.9;
  transform: scale(1.05);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
}

.item-value.market-group {
  color: #606266;
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
  background-color: #fef0f0;
  color: #f56c6c;
  border: 1px solid #fde2e2;
}

.meta-level-medium {
  background-color: #fdf6ec;
  color: #e6a23c;
  border: 1px solid #faecd8;
}

.meta-level-low {
  background-color: #f0f9ff;
  color: #67c23a;
  border: 1px solid #d9ecff;
}

.meta-level-default {
  background-color: #f4f4f5;
  color: #909399;
  border: 1px solid #e4e7ed;
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
  background: linear-gradient(135deg, #f5f7fa 0%, #f0f2f5 100%);
  color: #606266;
  border-radius: 6px;
  font-size: 13px;
  transition: all 0.2s ease;
  border: 1px solid #e4e7ed;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  position: relative;
}

.market-group-text:hover {
  background: linear-gradient(135deg, #e4e7ed 0%, #d3d4d6 100%);
  color: #303133;
  border-color: #c0c4cc;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.market-group-text.copyable {
  cursor: pointer;
}

.market-group-text.copyable:hover {
  background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
  color: #ffffff;
  border-color: #409eff;
  transform: translateY(-2px) scale(1.05);
  box-shadow: 0 4px 8px rgba(64, 158, 255, 0.3);
}

.market-group-text.copyable:active {
  transform: translateY(0) scale(1.02);
  box-shadow: 0 2px 4px rgba(64, 158, 255, 0.2);
}

.market-group-separator {
  display: inline-flex;
  align-items: center;
  color: #c0c4cc;
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
  border-top: 1px solid #ebeef5;
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
</style>