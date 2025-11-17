<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowRight } from '@element-plus/icons-vue'
import { http } from '@/http'
import { VueDraggable } from 'vue-draggable-plus'
import IndustryPlanPlanTable from './components/industryPlanPlanTable.vue'
import IndustryPlanConfigFlow from './components/industryPlanConfigFlow.vue'

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

// TODO: 删除计划

const deletePlanDialogVisible = ref(false)
const openDeletePlanDialog = () => {
  deletePlanDialogVisible.value = true
}
const cancelDeletePlan = () => {
  deletePlanDialogVisible.value = false
}


onMounted(() => {
  getMarketRootTree()
  getPlanTableData()
})


</script>

<template>
  <el-tabs class="industry-plan-tabs">
    <el-tab-pane label="计划管理">
      <div style="display: flex; flex-direction: row; justify-content: space-around; align-items: top;">
        <div class="market-root-tree-container">
          <el-scrollbar height="70vh">
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

        <div class="industry-plan-table-container" style="display: flex; flex-direction: horizontal; justify-content: flex-start;">
          <div class="industry-plan-table-product-list" style="min-width: 350px;">
            <div style="padding: 10px;">
              <span>当前计划: </span>
              <el-select
                placeholder="请选择计划"
                v-model="selectedPlan"
                style="width: 200px; margin-right: 10px;"
                :options="IndustryPlanTableData"
                :props="{value:'plan_name', label:'plan_name'}"
                @change="handlePlanChange"
              /><br/>
              <el-button @click="saveCurrentPlan">
                保存计划
              </el-button>
              <el-button @click="resetPlanModify">
                重置修改
              </el-button>
              <el-button @click="openCreatePlanDialog">
                新建计划
              </el-button>
              <el-button @click="openDeletePlanDialog">
                删除计划
              </el-button>
              <el-button @click="openModifyPlanDialog">
                修改计划设置
              </el-button>
            </div>
            <VueDraggable
              v-model="currentPlanProducts"
              target="tbody"
              :animation="150"
            >
              <industry-plan-plan-table :list="currentPlanProducts" />
            </VueDraggable>
          </div>
          <div class="industry-plan-table-fonfig-flow" style="min-width: 350px;">
            <industry-plan-config-flow v-if="selectedPlan" :selected-plan="selectedPlan" />
          </div>
        </div>
      </div>
    </el-tab-pane>
    <el-tab-pane label="配置">
      <!-- 配置内容待实现 -->
    </el-tab-pane>
  </el-tabs>

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
        <el-switch v-model="planForm.considerate_asset" />
      </el-form-item>
      
      <el-form-item label="是否考虑运行中任务">
        <el-switch v-model="planForm.considerate_running_job" />
      </el-form-item>
      
      <el-form-item label="是否按照习惯切分工作流">
        <el-switch v-model="planForm.split_to_jobs" />
      </el-form-item>
      
      <el-form-item label="是否考虑库存蓝图">
        <el-switch v-model="planForm.considerate_bp_relation" />
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
        <el-switch v-model="current_plan_settings.considerate_asset" />
      </el-form-item>
      
      <el-form-item label="是否考虑运行中任务">
        <el-switch v-model="current_plan_settings.considerate_running_job" />
      </el-form-item>
      
      <el-form-item label="是否按照习惯切分工作流">
        <el-switch v-model="current_plan_settings.split_to_jobs" />
      </el-form-item>
      
      <el-form-item label="是否考虑库存蓝图">
        <el-switch v-model="current_plan_settings.considerate_bp_relation" />
      </el-form-item>

      <el-form-item label="蓝图拷贝完全使用">
        <el-switch v-model="current_plan_settings.full_use_bp_cp" />
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
</template>

<style scoped>
.market-root-tree-container {
  background-color: #f5f7fa;
  min-width: 200px;
  width: 30%;
  max-width: 90vh;
  padding: 10px;
  margin-right: 10px;
  border-radius: 10px;
}
.industry-plan-table-container {
  width: 70%;
  background-color: #f5f7fa;
  padding: 10px;
}
.industry-plan-tabs {
  height: 80vh;
}
.industry-plan-table-fonfig-flow {
  width: 60%;
  background-color: #f5f7fa;
  padding: 10px;
  border-radius: 10px;
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
</style>