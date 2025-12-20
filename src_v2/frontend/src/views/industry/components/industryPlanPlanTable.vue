<template>
  <div class="table-container">
    <el-scrollbar class="table-scrollbar">

        <VueDraggable
          :model-value="list"
          @update:model-value="handleUpdateList"
          @start="handleDragStart"
          @end="handleDragEnd"
          item-key="row_id"
          target="tbody"
          :animation="150"
          handle=".drag-handle"
          class="industry-plan-product-table-draggable"
        >
        <table class="card-table" :class="{ 'compact-mode': cardStyleMode === 'compact' }">
        <thead>
          <tr class="table-header">
            <th>产品</th>
            <th>数量</th>
            <th>操作</th>
          </tr>
        </thead>
          <tbody class="industry-plan-product-table">
            <template v-for="item in list" :key="item.row_id">
              <!-- Group 行 -->
              <tr v-if="item.type === 'group'" class="card-row cursor-move group-row" :class="{ 
                'compact-mode': cardStyleMode === 'compact',
                'dragging': draggingGroupId === item.name
              }">
                <td colspan="2" class="group-header">
                  <div class="group-header-content" @click="toggleGroup(item.name || '')">
                    <span class="drag-handle cursor-move">☰</span>
                    <el-icon class="expand-icon" :class="{ 'expanded': isGroupExpanded(item.name || '') }">
                      <ArrowRight />
                    </el-icon>
                    <span class="group-name">{{ item.name }}</span>
                    <el-button size="small" @click.stop="handleEditGroup(item)"><el-icon><Edit /></el-icon></el-button>
                  </div>
                </td>
                <td class="action-cell" style="min-width: 150px;">
                  <el-switch
                    :model-value="getGroupActiveState(item.name || '')"
                    inline-prompt
                    active-text="启动"
                    inactive-text="关闭"
                    style="margin-right: 10px;"
                    :size="cardStyleMode === 'compact' ? 'small' : undefined"
                    @change="(val: boolean) => handleGroupActiveChange(item.name || '', val)"
                  />
                  <el-button 
                    v-if="cardStyleMode === 'normal'"
                    type="primary" 
                    plain 
                    @click="handleDeleteProduct(item)">
                    删除
                  </el-button>
                  <template v-else>
                    <el-button 
                      type="primary" 
                      plain 
                      :icon="ArrowUp"
                      circle
                      size="small"
                      @click="moveToTop(item)"
                      title="移动到顶层">
                    </el-button>
                    <el-button 
                      type="primary" 
                      plain 
                      :icon="ArrowDown"
                      circle
                      size="small"
                      @click="moveToBottom(item)"
                      title="移动到底层">
                    </el-button>
                    <el-button 
                      type="primary" 
                      plain 
                      :icon="Delete"
                      circle
                      size="small"
                      @click="handleDeleteProduct(item)">
                    </el-button>
                  </template>
                </td>
              </tr>
              <!-- 空组占位符行 -->
              <tr 
                v-if="item.type === 'group' && isGroupExpanded(item.name || '') && isGroupEmpty(item.name || '')"
                class="card-row group-placeholder-row"
                :class="{ 'compact-mode': cardStyleMode === 'compact' }"
              >
                <td colspan="3" class="placeholder-cell">
                  <div class="placeholder-content">
                    <span class="placeholder-text">拖入产品到这里</span>
                  </div>
                </td>
              </tr>
              <!-- Product 行 -->
              <tr 
                v-else-if="item.type === 'product'" 
                class="card-row cursor-move" 
                :class="{ 
                  'compact-mode': cardStyleMode === 'compact',
                  'group-product-row': item.group_id != null,
                  'dragging-with-group': draggingGroupId === item.group_id
                }"
                :style="{ display: item.group_id != null && !isGroupExpanded(item.group_id) ? 'none' : 'table-row' }"
              >
                <td class="product-name" :class="{ 'group-product-indent': item.group_id != null }">
                  <span 
                    v-if="draggingGroupId !== item.group_id || item.group_id == null" 
                    class="drag-handle cursor-move"
                  >☰</span>
                  {{ item.type_name_zh }}
                </td>
                <td class="quantity-cell">
                  <el-input-number
                    v-model="item.quantity"
                    :size="cardStyleMode === 'compact' ? 'small' : undefined"
                    controls-position="right" :min="0" :precision="0" />
                </td>
                <td style="min-width: 150px;" class="action-cell">
                  <el-switch
                    v-model="item.active"
                    inline-prompt
                    active-text="启动"
                    inactive-text="关闭"
                    :size="cardStyleMode === 'compact' ? 'small' : undefined"
                    @change="handleProductActiveChange"
                    style="margin-right: 10px;"
                  />
                  <el-button 
                    v-if="cardStyleMode === 'normal'"
                    type="primary" 
                    plain 
                    @click="handleDeleteProduct(item)">
                    删除
                  </el-button>
                  <template v-else>
                    <el-button 
                      type="primary" 
                      plain 
                      :icon="ArrowUp"
                      circle
                      size="small"
                      @click="moveToTop(item)"
                      title="移动到顶层">
                    </el-button>
                    <el-button 
                      type="primary" 
                      plain 
                      :icon="ArrowDown"
                      circle
                      size="small"
                      @click="moveToBottom(item)"
                      title="移动到底层">
                    </el-button>
                    <el-button 
                      type="primary" 
                      plain 
                      :icon="Delete"
                      circle
                      size="small"
                      @click="handleDeleteProduct(item)">
                    </el-button>
                  </template>
                </td>
              </tr>
            </template>
          </tbody>
        
      </table>
      </VueDraggable>
    </el-scrollbar>
    
    <!-- 编辑组名弹窗 -->
    <el-dialog
      v-model="editGroupDialogVisible"
      title="编辑组名"
      width="400px"
      @close="handleCancelEditGroup"
    >
      <el-input
        v-model="newGroupName"
        placeholder="请输入组名"
        @keyup.enter="handleConfirmEditGroup"
        clearable
      />
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="handleCancelEditGroup">取消</el-button>
          <el-button type="primary" @click="handleConfirmEditGroup">确定</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Delete, ArrowUp, ArrowDown, ArrowRight, Edit } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { VueDraggable } from 'vue-draggable-plus'

// 扁平化数据结构
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
  // group 属性
  name?: string                    // group 名称
  active?: boolean
}

interface Props {
  list: PlanRow[]
  cardStyleMode?: 'normal' | 'compact'
}
const props = withDefaults(defineProps<Props>(), {
  cardStyleMode: 'normal'
})

const emit = defineEmits<{
  (e: 'update:list', value: PlanRow[]): void
}>()

// 逻辑分组渲染
const groupedRows = computed(() => {
  const result: (PlanRow & { children?: PlanRow[] })[] = []
  const groupMap = new Map<string, PlanRow & { children: PlanRow[] }>()
  
  for (const row of props.list) {
    if (row.type === 'group') {
      const group = { ...row, children: [] }
      groupMap.set(row.name || '', group)
      result.push(group)
    } else if (row.group_id != null && groupMap.has(row.group_id)) {
      groupMap.get(row.group_id)!.children!.push(row)
    } else {
      result.push(row)
    }
  }
  
  return result
})

const handleUpdateList = (newList: PlanRow[]) => {
  console.log("handleUpdateList", newList)
  // 更新 order
  newList.forEach((row, idx) => {
    row.order = idx
  })
  emit('update:list', newList)
}

// 拖拽开始处理
const handleDragStart = (evt: any) => {
  const draggedRow = props.list[evt.oldIndex]
  if (draggedRow.type === 'group') {
    draggingGroupId.value = draggedRow.name || null
  }
}

// 拖拽结束处理：检测拖入/拖出组
const handleDragEnd = (evt: any) => {
  const { oldIndex, newIndex } = evt
  if (oldIndex === newIndex) {
    draggingGroupId.value = null
    return
  }
  
  const draggedRow = props.list[oldIndex]

  // 优先处理整组拖动
  if (draggedRow.type === 'group') {
    moveGroupBlock(draggedRow.name || '', newIndex)
    draggingGroupId.value = null
    return
  }

  // 原有的 product 拖拽逻辑（拖入组/拖出组）
  const reordered = [...props.list]
  const [removed] = reordered.splice(oldIndex, 1)
  reordered.splice(newIndex, 0, removed)
  
  // 更新 order
  reordered.forEach((row, idx) => {
    row.order = idx
  })
  
  // 检测目标位置是否在组内
  let targetGroupId: string | null = null
  
  // 只处理 product 类型的拖拽
  if (removed.type === 'product') {
    // 向前查找最近的 group
    let nearestGroupIndex = -1
    for (let i = newIndex - 1; i >= 0; i--) {
      if (reordered[i].type === 'group') {
        nearestGroupIndex = i
        targetGroupId = reordered[i].name || null
        console.log("找到最近的group", reordered[i])
        break
      }
    }
    
    // 如果找到了 group，检查新位置是否真的在该组内
    if (nearestGroupIndex >= 0 && targetGroupId != null) {
      // 检查新位置之后是否有其他 group 或不属于该组的产品
      // 如果新位置之后有另一个 group，说明拖到了组外
      // 如果新位置之后有独立产品（group_id=null），说明拖到了组外
      // 如果新位置之后有属于其他组的产品，说明拖到了组外
      let isInGroup = true
      let skip = false
      
      // 特殊处理：如果新位置紧跟在组行之后（newIndex === nearestGroupIndex + 1）
      // 且组内没有其他产品，应该认为是在组内（允许拖入空组）
      if (newIndex === nearestGroupIndex + 1) {
        // 检查组内是否有其他产品（排除当前被拖拽的产品）
        const groupHasOtherProducts = reordered.some((row, idx) => 
          idx !== newIndex && 
          row.type === 'product' && 
          row.group_id === targetGroupId
        )
        // 如果组内没有其他产品，且位置紧跟在组行之后，认为是在组内
        if (!groupHasOtherProducts) {
          console.log("拖入空组：位置紧跟在组行之后，且组内没有其他产品，认为是在组内")
          skip = true
        } else {
          // 组内有其他产品，继续后续检查
          console.log("组内有其他产品，继续后续检查")
        }
      }
      
      // 如果已经确定不在组内，跳过后续检查
      if (!skip) {
        // 查找该组的所有产品范围（从 group 行到下一个 group 或独立产品之前）
        // 移动到最后一位，认为移出
        if (newIndex === reordered.length - 1) {
          isInGroup = false
        } else {
          for (let i = newIndex + 1; i < reordered.length; i++) {
            if (reordered[i].type === 'group') {
              // 遇到另一个 group，说明不在原组内
              console.log("如果新位置之后有另一个 group，说明拖到了组外")
              isInGroup = false
              break
            } else if (reordered[i].type === 'product') {
              if (reordered[i].group_id === targetGroupId) {
                console.log("如果遇到的产品属于该组，说明还在该组范围内")
                break
              }
              // 如果遇到的产品是独立产品（group_id=null），说明已经超出该组范围
              if (reordered[i].group_id == null) {
                console.log("如果遇到的产品是独立产品（group_id=null），说明已经超出该组范围", reordered)
                console.log("i=", i)
                isInGroup = false
                break
              }
              // 如果遇到的产品属于其他组，说明已经超出该组范围
              if (reordered[i].group_id !== targetGroupId) {
                console.log("如果遇到的产品属于其他组，说明已经超出该组范围")
                isInGroup = false
                break
              }
            }
          }
        }
      }
      
      // 如果不在组内，清除 group_id
      if (!isInGroup) {
        targetGroupId = null
      }
    }
    // 如果没有找到 group，targetGroupId 已经是 null，表示拖到了组外
    
    // 更新 group_id
    removed.group_id = targetGroupId
    
    console.log(`拖拽完成: 从位置 ${oldIndex} 到 ${newIndex}, group_id: ${targetGroupId}`)
  }
  
  draggingGroupId.value = null
  emit('update:list', reordered)
}

// 展开状态管理
const expandedGroups = ref<Set<string>>(new Set())

// 拖动状态管理
const draggingGroupId = ref<string | null>(null)

// 编辑组名弹窗状态管理
const editGroupDialogVisible = ref(false)
const editingGroup = ref<PlanRow | null>(null)
const newGroupName = ref('')

const toggleGroup = (groupName: string) => {
  if (expandedGroups.value.has(groupName)) {
    expandedGroups.value.delete(groupName)
  } else {
    expandedGroups.value.add(groupName)
  }
}

const isGroupExpanded = (groupName: string) => {
  return expandedGroups.value.has(groupName)
}

// 获取组内产品
const getGroupProducts = (groupName: string): PlanRow[] => {
  return props.list.filter(row => row.type === 'product' && row.group_id === groupName)
}

// 检查组是否为空
const isGroupEmpty = (groupName: string): boolean => {
  return getGroupProducts(groupName).length === 0
}

// 获取组内所有product的active状态
const getGroupActiveState = (groupName: string): boolean => {
  const groupProducts = getGroupProducts(groupName)
  if (groupProducts.length === 0) return false
  // 如果所有product都是active（不为false），返回true；否则返回false
  return groupProducts.every(p => p.active !== false)
}

// 处理group开关变化
const handleGroupActiveChange = (groupName: string, newValue: boolean) => {
  const newList = [...props.list]
  newList.forEach(row => {
    if (row.type === 'product' && row.group_id === groupName) {
      row.active = newValue
    }
  })
  handleUpdateList(newList)
}

// 处理product开关变化
const handleProductActiveChange = () => {
  // 直接使用handleUpdateList更新，因为v-model已经更新了item.active
  handleUpdateList([...props.list])
}

/**
 * 获取组的完整区间 [start, end)
 * @param rows 行数组
 * @param groupName 组名称
 * @returns { start: number, end: number } | null
 */
function getGroupBlock(rows: PlanRow[], groupName: string): { start: number, end: number } | null {
  const start = rows.findIndex(r => r.type === 'group' && r.name === groupName)
  if (start === -1) return null

  let end = start + 1
  while (
    end < rows.length &&
    rows[end].type === 'product' &&
    rows[end].group_id === groupName
  ) {
    end++
  }

  return { start, end }
}

/**
 * 移动整个组块
 * @param groupName 组名称
 * @param targetIndex 目标位置
 */
function moveGroupBlock(groupName: string, targetIndex: number) {
  console.log('=== moveGroupBlock 开始 ===')
  console.log('groupName:', groupName, 'targetIndex:', targetIndex)
  
  const rows = [...props.list]
  console.log('原始列表长度:', rows.length)
  console.log('原始列表:', rows.map(r => ({ type: r.type, row_id: r.row_id, group_id: r.group_id, order: r.order })))
  
  const block = getGroupBlock(rows, groupName)
  console.log('获取到的组块:', block)
  if (!block) {
    console.log('未找到组块，退出')
    return
  }

  const { start, end } = block
  console.log(`组块区间: [${start}, ${end})，包含 ${end - start} 行`)
  console.log('组块内容:', rows.slice(start, end).map(r => ({ type: r.type, row_id: r.row_id, group_id: r.group_id })))

  // 防止拖进自己内部（在删除之前检查）
  if (targetIndex > start && targetIndex < end) {
    console.log(`目标位置 ${targetIndex} 在组块内部 [${start}, ${end})，禁止拖进自己，退出`)
    emit('update:list', rows)
    return // 拖进自己，直接返回
  }
  console.log(`目标位置 ${targetIndex} 在组块外部，允许移动`)

  const blockRows = rows.slice(start, end)
  console.log('准备移动的组块行数:', blockRows.length)

  // 先删除整块
  rows.splice(start, end - start)
  console.log('删除组块后的列表长度:', rows.length)
  console.log('删除组块后的列表:', rows.map(r => ({ type: r.type, row_id: r.row_id, group_id: r.group_id, order: r.order })))

  // 修正目标 index（如果向下拖）
  let insertIndex = targetIndex
  if (insertIndex > start) {
    const offset = end - start - 1
    insertIndex -= offset
    console.log(`向下拖动，修正插入位置: ${targetIndex} -> ${insertIndex} (偏移量: ${offset})`)
  } else {
    console.log(`向上拖动，插入位置不变: ${insertIndex}`)
  }

  // 插入整块
  rows.splice(insertIndex, 0, ...blockRows)
  console.log('插入组块后的列表长度:', rows.length)
  console.log('插入组块后的列表:', rows.map(r => ({ type: r.type, row_id: r.row_id, group_id: r.group_id, order: r.order })))

  // 重排 order
  rows.forEach((r, i) => (r.order = i))
  console.log('重排 order 后的列表:', rows.map(r => ({ type: r.type, row_id: r.row_id, group_id: r.group_id, order: r.order })))

  console.log('=== moveGroupBlock 结束，发送更新 ===')
  emit('update:list', rows)
}

// 删除产品
const handleDeleteProduct = async (item: PlanRow) => {
  if (item.type === 'group') {
    const groupProducts = getGroupProducts(item.name || '')
    const productCount = groupProducts.length
    
    try {
      await ElMessageBox.confirm(
        `确定要删除组 "${item.name}" 吗？组内包含 ${productCount} 个产品，删除后将同时删除组内所有产品。点击保存计划后生效。`,
        '删除组',
        {
          confirmButtonText: '确定删除',
          cancelButtonText: '取消',
          type: 'warning'
        }
      )
      
      // 删除组和所有组内产品
      const newList = props.list.filter(row => 
        row.row_id !== item.row_id && 
        row.group_id !== item.name
      )
      handleUpdateList(newList)
    } catch {
      // 用户取消，不执行删除
    }
  } else {
    // 原有逻辑：删除单个产品
    const newList = props.list.filter(row => row.row_id !== item.row_id)
    handleUpdateList(newList)
  }
}

// 移动到顶部
const moveToTop = (item: PlanRow) => {
  if (item.type === 'group') {
    // 移动整组到顶层
    moveGroupBlock(item.name || '', 0)
    return
  }
  
  // 产品移动
  const newList = [...props.list]
  const index = newList.findIndex(row => row.row_id === item.row_id)
  if (index === -1) return
  
  if (item.group_id == null) {
    // 独立产品：移动到计划顶层
    const [removed] = newList.splice(index, 1)
    newList.unshift(removed)
  } else {
    // 组内产品：移动到组的第一位
    const block = getGroupBlock(newList, item.group_id)
    if (!block) return
    
    // 计算目标位置（组的第一位，紧跟在组行之后）
    const targetIndex = block.start + 1
    
    // 如果已经在目标位置，不需要移动
    if (index === targetIndex) return
    
    const [removed] = newList.splice(index, 1)
    // 组内产品的索引总是 >= targetIndex，所以移除后插入位置就是 targetIndex
    newList.splice(targetIndex, 0, removed) // 插入到组行之后
  }
  
  handleUpdateList(newList)
}

// 移动到底部
const moveToBottom = (item: PlanRow) => {
  if (item.type === 'group') {
    // 移动整组到底层
    moveGroupBlock(item.name || '', props.list.length)
    return
  }
  
  // 产品移动
  const newList = [...props.list]
  const index = newList.findIndex(row => row.row_id === item.row_id)
  if (index === -1) return
  
  if (item.group_id == null) {
    // 独立产品：移动到计划底层
    const [removed] = newList.splice(index, 1)
    newList.push(removed)
  } else {
    // 组内产品：移动到组的最后一位
    const block = getGroupBlock(newList, item.group_id)
    if (!block) return
    
    // 计算目标位置（组的最后一位）
    const targetIndex = block.end
    
    // 如果已经在目标位置，不需要移动
    if (index === targetIndex) return
    
    const [removed] = newList.splice(index, 1)
    // 如果从目标位置之前移除，插入位置需要减1
    const insertIndex = index < targetIndex ? targetIndex - 1 : targetIndex
    newList.splice(insertIndex, 0, removed) // 插入到组块末尾之前
  }
  
  handleUpdateList(newList)
}

// 编辑组名
const handleEditGroup = (group: PlanRow) => {
  editingGroup.value = group
  newGroupName.value = group.name || ''
  editGroupDialogVisible.value = true
}

// 确认编辑组名
const handleConfirmEditGroup = () => {
  if (!editingGroup.value) return
  
  // 验证输入
  const trimmedName = newGroupName.value.trim()
  if (!trimmedName) {
    return
  }
  
  // 更新组名
  const newList = [...props.list]
  const groupIndex = newList.findIndex(row => row.row_id === editingGroup.value!.row_id)
  if (groupIndex !== -1) {
    const oldGroupName = newList[groupIndex].name || ''
    newList[groupIndex].name = trimmedName
    
    // 更新所有相关product的group_id
    newList.forEach(row => {
      if (row.type === 'product' && row.group_id === oldGroupName) {
        row.group_id = trimmedName
      }
    })
    
    // 更新展开状态：如果旧组名是展开的，保持新组名的展开状态
    if (expandedGroups.value.has(oldGroupName)) {
      expandedGroups.value.delete(oldGroupName)
      expandedGroups.value.add(trimmedName)
    }
    
    handleUpdateList(newList)
  }
  
  // 关闭弹窗
  editGroupDialogVisible.value = false
  editingGroup.value = null
  newGroupName.value = ''
}

// 取消编辑组名
const handleCancelEditGroup = () => {
  editGroupDialogVisible.value = false
  editingGroup.value = null
  newGroupName.value = ''
}

</script>

<style scoped>
.table-container {
  width: 100%;
  height: 100%;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.table-scrollbar {
  flex: 1;
  min-height: 0;
}

.card-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0 8px;
  background: transparent;
}

.card-table.compact-mode {
  border-spacing: 0;
}

.table-header {
  background: transparent;
}

.table-header th {
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  font-size: 14px;
  color: #606266;
  border: none;
  background: transparent;
}

.industry-plan-product-table {
  display: table-row-group;
}

.card-row {
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  margin-bottom: 12px;
  display: table-row;
  border: none;
}

.card-row:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  transform: translateY(-2px);
  background: #ffffff;
}

.card-row td {
  padding: 10px;
  border: none;
  background: transparent;
  vertical-align: middle;
}

.card-row.compact-mode td {
  padding: 1px 8px;
  height: calc(1em + 2px);
  line-height: 1em;
}

.card-row:first-child td:first-child {
  border-top-left-radius: 12px;
}

.card-row:first-child td:last-child {
  border-top-right-radius: 12px;
}

.card-row:last-child td:first-child {
  border-bottom-left-radius: 12px;
}

.card-row:last-child td:last-child {
  border-bottom-right-radius: 12px;
}

.product-name {
  font-size: 15px;
  font-weight: 500;
  color: #303133;
  min-width: 100px;
}

.compact-mode .product-name {
  font-size: 14px;
}

.quantity-cell {
  width: 250px;
}

.quantity-cell :deep(.el-input-number) {
  width: 100%;
}

.quantity-cell :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #dcdfe6 inset;
  border-radius: 4px;
  transition: all 0.2s;
}

.quantity-cell :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #c0c4cc inset;
}

.action-cell {
  width: 40px;
  min-width: 40px;
  text-align: right;
}

.action-cell .el-button {
  transition: all 0.2s;
}

.action-cell .el-button:hover {
  transform: scale(1.05);
}

.compact-mode .action-cell {
  width: auto;
  display: flex;
  gap: 4px;
  justify-content: flex-end;
}

.compact-mode .action-cell .el-button {
  padding: 4px;
  min-height: auto;
  margin-left: 0;
}

/* 拖拽时的视觉反馈 */
.card-row.sortable-ghost {
  opacity: 0.5;
  background: #f5f7fa;
}

.card-row.sortable-drag {
  opacity: 0.8;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
}

/* 整组拖动时的视觉特效 */
.group-row.dragging,
.group-product-row.dragging-with-group {
  opacity: 0.6;
  transform: scale(0.98);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  background: #f0f9ff;
  border-left: 3px solid #409eff;
}

.group-row.sortable-drag {
  opacity: 0.9;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.24);
  transform: scale(1.02);
}

/* 拖动时隐藏组内产品的拖拽手柄（避免误操作） */
.group-product-row.dragging-with-group .drag-handle {
  display: none;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .table-container {
    padding: 4px 0;
  }

  .card-table {
    border-spacing: 0 8px;
  }

  .card-row td {
    padding: 12px;
  }

  .product-name {
    min-width: 150px;
    font-size: 14px;
  }

  .quantity-cell {
    width: 140px;
  }

  .action-cell {
    width: 100px;
  }

  .table-header th {
    padding: 10px 12px;
    font-size: 13px;
  }
}

/* 空状态优化 */
.industry-plan-product-table:empty::after {
  content: '暂无产品';
  display: block;
  text-align: center;
  padding: 40px;
  color: #909399;
  font-size: 14px;
}

/* Group 行样式 */
.group-row {
  background: #ffffff;
}

.group-header {
  padding: 10px;
}

.group-header-content {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.group-header-content:hover {
  opacity: 0.8;
}

.expand-icon {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  font-size: 14px;
  color: #606266;
  flex-shrink: 0;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.group-name {
  font-size: 15px;
  font-weight: 500;
  color: #303133;
}

.compact-mode .group-name {
  font-size: 14px;
}

/* 组内产品样式 */
.group-product-row {
  background: #f8f9fa;
  border-left: 2px solid #e4e7ed;
}

.group-product-row:hover {
  background: #f0f2f5;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  transform: translateY(-2px);
}

.group-product-row td:first-child {
  padding-left: 32px;
}

.group-product-row.compact-mode td:first-child {
  padding-left: 24px;
}

.group-product-indent {
  padding-left: 32px !important;
}

.compact-mode .group-product-indent {
  padding-left: 24px !important;
}

/* 空组占位符样式 */
.group-placeholder-row {
  background: transparent !important;
  box-shadow: none !important;
  border: 2px dashed #dcdfe6;
  border-radius: 8px;
  margin: 4px 0;
}

.group-placeholder-row:hover {
  border-color: #409eff;
  background: #f0f9ff !important;
  transform: none !important;
}

.placeholder-cell {
  padding: 20px !important;
  text-align: center;
}

.compact-mode .placeholder-cell {
  padding: 12px !important;
}

.placeholder-content {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
}

.placeholder-text {
  color: #909399;
  font-size: 14px;
  font-weight: 400;
  user-select: none;
}

.compact-mode .placeholder-text {
  font-size: 12px;
}

.group-placeholder-row:hover .placeholder-text {
  color: #409eff;
}
</style>