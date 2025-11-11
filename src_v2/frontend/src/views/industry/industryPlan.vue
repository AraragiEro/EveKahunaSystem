<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { http } from '@/http'
import { VueDraggable } from 'vue-draggable-plus'
import IndustryPlanPlanTable from './components/industryPlanPlanTable.vue'

interface PlanProductTableData {
  "row_id": number,
  "index_id": number,
  "product_type_id": number,
  "quantity": number,
  "type_name": string,
  "type_name_zh": string
}

interface PlanTableData {
  "row_id": number,
  "plan_name": string,
  "user_name": string,
  "plan_settings": object,
  "products": PlanProductTableData[]
}

const marketRootTree = ref([])
const selectedPlan = ref<string | null>(null)
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
  const res = await http.post('/EVE/industry/getPlanTableData')
  const data = await res.json()
  IndustryPlanTableData.value = data.data
  if (selectedPlan.value) {
    currentPlanProducts.value = IndustryPlanTableData.value.find(item => item.plan_name == selectedPlan.value)?.products || []
  } else {
    currentPlanProducts.value = []
  }
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
const handleAddPlan = (command: string) => {
  console.log("handleAddPlan", command)
  addPlanDialogVisible.value = true
  addPlanDialogForm.value.type_id = command

  addPlanDialogForm.value.get_plan_loading = true
  getPlanTableData()
  addPlanDialogForm.value.plan_list = IndustryPlanTableData.value
  addPlanDialogForm.value.get_plan_loading = false
}

const handleAddPlanConfirm = async () => {
  addPlanDialogForm.value.add_plan_loading = true
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
  currentPlanProducts.value = IndustryPlanTableData.value.find(item => item.plan_name == value)?.products || []
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
          <el-scrollbar height="90vh">
            <el-table
              ref="marketRootTreeRef"
              @row-click="handleRowClick"
              class="market-root-tree-table"
              :data="marketRootTree"
              lazy
              row-key="row_id"
              :load="loadChildTree"
            >
              <el-table-column prop="name" label="名称">
                <template #default="scope">
                  <span
                    v-if="scope.row.can_add_plan == false"
                    style="color: gray; cursor: not-allowed;"
                  >
                    {{ scope.row.name }}
                  </span>
                  <el-dropdown
                    v-else-if="scope.row.can_add_plan == true"
                    trigger="contextmenu"
                    size="large"
                    @command="handleAddPlan"
                  >
                    <span>
                      {{ scope.row.name }}
                    </span>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item :command="scope.row.type_id">添加到计划</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                  <span v-else>
                    {{ scope.row.name}}
                  </span>
                </template>
              </el-table-column>
            </el-table>
        </el-scrollbar>
        </div>
        <div class="industry-plan-table-container" style="display: flex; flex-direction: horizontal; justify-content: flex-start;">
          <div class="industry-plan-table-product-list">
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
            </div>
            <VueDraggable
              v-model="currentPlanProducts"
              target="tbody"
              :animation="150"
            >
              <industry-plan-plan-table :list="currentPlanProducts" />
            </VueDraggable>
          </div>
          <div class="industry-plan-table-fonfig-flow">
            配置流
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
  height: 86vh;
}
</style>