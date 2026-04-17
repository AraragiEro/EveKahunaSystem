<template>
  <div class="plan-table-container" :class="{ compact: cardStyleMode === 'compact' }">
    <el-scrollbar class="plan-scrollbar">
      <VueDraggable
        v-model="topLevelItems"
        item-key="key"
        :group="{ name: 'plan-top', pull: true, put: ['plan-top', 'plan-products'] }"
        handle=".top-drag-handle"
        :animation="180"
        ghost-class="drag-ghost"
        chosen-class="drag-chosen"
        class="top-level-list"
        :move="handleTopLevelMove"
        @end="emitFlattened"
      >
        <div v-for="item in topLevelItems" :key="item.key" class="top-level-item">
          <template v-if="item.type === 'group'">
            <div class="group-card">
              <div class="group-header">
                <div class="group-title" @click="toggleGroup(item.name || '')">
                  <span class="top-drag-handle">☰</span>
                  <el-icon class="expand-icon" :class="{ expanded: isGroupExpanded(item.name || '') }">
                    <ArrowRight />
                  </el-icon>
                  <span class="group-name">{{ item.name || '未命名分组' }}</span>
                </div>
                <div class="group-actions">
                  <el-switch
                    :model-value="getGroupActiveState(item)"
                    inline-prompt
                    active-text="启用"
                    inactive-text="关闭"
                    :size="cardStyleMode === 'compact' ? 'small' : undefined"
                    @change="(val: boolean) => handleGroupActiveChange(item, val)"
                  />
                  <el-button size="small" :icon="Edit" circle @click="handleEditGroup(item)" />
                  <el-button size="small" :icon="Delete" circle @click="handleDeleteGroup(item)" />
                </div>
              </div>

              <div v-show="isGroupExpanded(item.name || '')" class="group-body">
                <VueDraggable
                  v-model="item.products"
                  item-key="key"
                  :group="{ name: 'plan-products', pull: true, put: ['plan-products', 'plan-top'] }"
                  handle=".product-drag-handle"
                  :animation="180"
                  ghost-class="drag-ghost"
                  chosen-class="drag-chosen"
                  class="product-list"
                  :move="handleGroupMove"
                  @end="emitFlattened"
                >
                  <div
                    v-for="product in item.products"
                    :key="product.key"
                    class="product-card grouped"
                    :class="{ compact: cardStyleMode === 'compact' }"
                  >
                    <div class="product-main">
                      <span class="product-drag-handle">☰</span>
                      <span class="product-name">{{ product.type_name_zh || product.type_name || '-' }}</span>
                    </div>
                    <div class="product-controls">
                      <el-input-number
                        v-model="product.quantity"
                        controls-position="right"
                        :min="0"
                        :precision="0"
                        :size="cardStyleMode === 'compact' ? 'small' : undefined"
                        @change="emitFlattened"
                      />
                      <el-switch
                        v-model="product.active"
                        inline-prompt
                        active-text="启用"
                        inactive-text="关闭"
                        :size="cardStyleMode === 'compact' ? 'small' : undefined"
                        @change="emitFlattened"
                      />
                      <el-button size="small" :icon="Delete" circle @click="handleDeleteProduct(product, item)" />
                    </div>
                  </div>
                </VueDraggable>
                <div v-if="item.products.length === 0" class="empty-dropzone">拖入产品到该分组</div>
              </div>
            </div>
          </template>

          <template v-else>
            <div class="product-card top-level-product" :class="{ compact: cardStyleMode === 'compact' }">
              <div class="product-main">
                <span class="top-drag-handle">☰</span>
                <span class="product-name">{{ item.type_name_zh || item.type_name || '-' }}</span>
              </div>
              <div class="product-controls">
                <el-input-number
                  v-model="item.quantity"
                  controls-position="right"
                  :min="0"
                  :precision="0"
                  :size="cardStyleMode === 'compact' ? 'small' : undefined"
                  @change="emitFlattened"
                />
                <el-switch
                  v-model="item.active"
                  inline-prompt
                  active-text="启用"
                  inactive-text="关闭"
                  :size="cardStyleMode === 'compact' ? 'small' : undefined"
                  @change="emitFlattened"
                />
                <el-button size="small" :icon="Delete" circle @click="handleDeleteTopLevelProduct(item)" />
              </div>
            </div>
          </template>
        </div>
      </VueDraggable>
    </el-scrollbar>

    <el-dialog
      v-model="editGroupDialogVisible"
      title="编辑分组名称"
      width="420px"
      @close="handleCancelEditGroup"
    >
      <el-input
        v-model="newGroupName"
        placeholder="请输入分组名称"
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
import { ref, watch } from 'vue'
import { ArrowRight, Delete, Edit } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { VueDraggable } from 'vue-draggable-plus'

interface PlanRow {
  row_id: number
  type: 'group' | 'product'
  group_id?: string | null
  order: number
  type_id?: number
  quantity?: number
  type_name?: string
  type_name_zh?: string
  name?: string
  active?: boolean
}

interface LocalProductRow extends PlanRow {
  type: 'product'
  key: string
  quantity: number
  active: boolean
  group_id: string | null
}

interface LocalGroupRow extends PlanRow {
  type: 'group'
  key: string
  name: string
  products: LocalProductRow[]
}

type TopLevelItem = LocalProductRow | LocalGroupRow

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

const topLevelItems = ref<TopLevelItem[]>([])
const expandedGroups = ref<Set<string>>(new Set())

const editGroupDialogVisible = ref(false)
const editingGroup = ref<LocalGroupRow | null>(null)
const newGroupName = ref('')

const productKey = (row: PlanRow, index: number) => `product-${row.row_id}-${index}-${Math.random().toString(36).slice(2, 8)}`
const groupKey = (row: PlanRow, index: number) => `group-${row.row_id}-${index}-${Math.random().toString(36).slice(2, 8)}`

const toLocalProduct = (row: PlanRow, index: number): LocalProductRow => ({
  ...row,
  type: 'product',
  key: productKey(row, index),
  quantity: row.quantity ?? 0,
  active: row.active !== false,
  group_id: row.group_id ?? null
})

const toLocalGroup = (row: PlanRow, index: number): LocalGroupRow => ({
  ...row,
  type: 'group',
  key: groupKey(row, index),
  name: row.name || '',
  group_id: null,
  products: []
})

const rebuildFromProps = (rows: PlanRow[]) => {
  const nextTopLevel: TopLevelItem[] = []
  const groupMap = new Map<string, LocalGroupRow>()

  rows.forEach((row, idx) => {
    if (row.type === 'group') {
      const group = toLocalGroup(row, idx)
      nextTopLevel.push(group)
      groupMap.set(group.name, group)
      return
    }

    const product = toLocalProduct(row, idx)
    if (product.group_id && groupMap.has(product.group_id)) {
      groupMap.get(product.group_id)!.products.push(product)
      return
    }
    product.group_id = null
    nextTopLevel.push(product)
  })

  const validExpanded = new Set<string>()
  nextTopLevel.forEach((item) => {
    if (item.type !== 'group') return
    if (expandedGroups.value.has(item.name)) validExpanded.add(item.name)
  })
  if (validExpanded.size === 0) {
    nextTopLevel.forEach((item) => {
      if (item.type === 'group') validExpanded.add(item.name)
    })
  }

  expandedGroups.value = validExpanded
  topLevelItems.value = nextTopLevel
}

watch(
  () => props.list,
  (rows) => rebuildFromProps(rows || []),
  { immediate: true, deep: true }
)

const emitFlattened = () => {
  const flat: PlanRow[] = []
  let order = 0

  topLevelItems.value.forEach((item) => {
    if (item.type === 'group') {
      flat.push({
        row_id: item.row_id,
        type: 'group',
        name: item.name,
        group_id: null,
        order: order++
      })
      item.products.forEach((product) => {
        flat.push({
          row_id: product.row_id,
          type: 'product',
          type_id: product.type_id,
          quantity: product.quantity,
          type_name: product.type_name,
          type_name_zh: product.type_name_zh,
          group_id: item.name,
          active: product.active,
          order: order++
        })
      })
      return
    }

    flat.push({
      row_id: item.row_id,
      type: 'product',
      type_id: item.type_id,
      quantity: item.quantity,
      type_name: item.type_name,
      type_name_zh: item.type_name_zh,
      group_id: null,
      active: item.active,
      order: order++
    })
  })

  emit('update:list', flat)
}

const handleTopLevelMove = (evt: any) => {
  const dragged = evt?.draggedContext?.element as TopLevelItem | LocalProductRow | undefined
  return dragged?.type === 'group' || dragged?.type === 'product'
}

const handleGroupMove = (evt: any) => {
  const dragged = evt?.draggedContext?.element as TopLevelItem | LocalProductRow | undefined
  return dragged?.type === 'product'
}

const toggleGroup = (groupName: string) => {
  if (expandedGroups.value.has(groupName)) {
    expandedGroups.value.delete(groupName)
  } else {
    expandedGroups.value.add(groupName)
  }
}

const isGroupExpanded = (groupName: string) => expandedGroups.value.has(groupName)

const getGroupActiveState = (group: LocalGroupRow) => {
  if (group.products.length === 0) return false
  return group.products.every((item) => item.active !== false)
}

const handleGroupActiveChange = (group: LocalGroupRow, value: boolean) => {
  group.products.forEach((item) => {
    item.active = value
  })
  emitFlattened()
}

const handleDeleteGroup = async (group: LocalGroupRow) => {
  try {
    const groupName = group.name || '未命名分组'
    await ElMessageBox.confirm(
      `确定删除分组 "${groupName}" 及其组内全部产品吗？点击保存计划后生效。`,
      '删除分组',
      {
        type: 'warning',
        confirmButtonText: '确定删除',
        cancelButtonText: '取消'
      }
    )
    const index = topLevelItems.value.findIndex((item) => item.type === 'group' && item.key === group.key)
    if (index >= 0) {
      topLevelItems.value.splice(index, 1)
      emitFlattened()
    }
  } catch {
    // 用户取消
  }
}

const handleDeleteProduct = (product: LocalProductRow, group: LocalGroupRow) => {
  const index = group.products.findIndex((item) => item.key === product.key)
  if (index >= 0) {
    group.products.splice(index, 1)
    emitFlattened()
  }
}

const handleDeleteTopLevelProduct = (product: LocalProductRow) => {
  const index = topLevelItems.value.findIndex((item) => item.type === 'product' && item.key === product.key)
  if (index >= 0) {
    topLevelItems.value.splice(index, 1)
    emitFlattened()
  }
}

const handleEditGroup = (group: LocalGroupRow) => {
  editingGroup.value = group
  newGroupName.value = group.name || ''
  editGroupDialogVisible.value = true
}

const handleConfirmEditGroup = () => {
  if (!editingGroup.value) return
  const name = newGroupName.value.trim()
  if (!name) return

  const oldName = editingGroup.value.name
  editingGroup.value.name = name

  if (expandedGroups.value.has(oldName)) {
    expandedGroups.value.delete(oldName)
    expandedGroups.value.add(name)
  }

  editGroupDialogVisible.value = false
  editingGroup.value = null
  newGroupName.value = ''
  emitFlattened()
}

const handleCancelEditGroup = () => {
  editGroupDialogVisible.value = false
  editingGroup.value = null
  newGroupName.value = ''
}
</script>

<style scoped>
.plan-table-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.plan-scrollbar {
  flex: 1;
  min-height: 0;
}

.top-level-list,
.product-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 4px 12px;
}

.group-card {
  border: 1px solid var(--k-color-border);
  background: var(--k-color-surface);
  border-radius: 10px;
  padding: 10px;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
  min-width: 0;
}

.group-name {
  font-weight: 600;
  color: var(--k-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.group-body {
  margin-top: 10px;
}

.top-drag-handle,
.product-drag-handle {
  cursor: grab;
  color: var(--k-color-text-secondary);
}

.product-card {
  border: 1px solid var(--k-color-border);
  border-radius: 8px;
  background: var(--k-color-surface-soft);
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.top-level-product {
  background: var(--k-color-surface);
}

.grouped {
  border-left: 3px solid color-mix(in srgb, var(--k-color-primary) 45%, var(--k-color-border));
}

.product-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.product-name {
  color: var(--k-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.product-controls :deep(.el-input-number) {
  width: 140px;
}

.plan-table-container :deep(.el-input-number) {
  --el-input-bg-color: var(--k-color-surface-soft);
  --el-fill-color-blank: var(--k-color-surface-soft);
}

.plan-table-container :deep(.el-input-number .el-input__wrapper) {
  background: var(--k-color-surface-soft) !important;
  box-shadow: 0 0 0 1px var(--k-color-border) inset !important;
}

.plan-table-container :deep(.el-input-number .el-input__inner) {
  color: var(--k-color-text) !important;
  font-weight: 600;
}

.plan-table-container :deep(.el-input-number__decrease),
.plan-table-container :deep(.el-input-number__increase) {
  background: color-mix(in srgb, var(--k-color-surface-soft) 88%, var(--k-color-surface)) !important;
  border-color: var(--k-color-border) !important;
  color: var(--k-color-text-secondary) !important;
}

.plan-table-container :deep(.el-input-number__decrease:hover),
.plan-table-container :deep(.el-input-number__increase:hover) {
  color: var(--k-color-primary) !important;
  background: color-mix(in srgb, var(--k-color-primary) 12%, var(--k-color-surface-soft)) !important;
}

.plan-table-container :deep(.el-input-number.is-disabled .el-input__wrapper),
.plan-table-container :deep(.el-input-number.is-disabled .el-input-number__decrease),
.plan-table-container :deep(.el-input-number.is-disabled .el-input-number__increase) {
  background: color-mix(in srgb, var(--k-color-surface-soft) 70%, var(--k-color-surface)) !important;
  color: var(--k-color-text-secondary) !important;
  border-color: var(--k-color-border) !important;
  opacity: 0.7;
}

.empty-dropzone {
  border: 1px dashed var(--k-color-border);
  border-radius: 8px;
  padding: 12px;
  color: var(--k-color-text-secondary);
  text-align: center;
  font-size: 13px;
}

.expand-icon {
  transition: transform 0.2s ease;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.drag-ghost {
  opacity: 0.45;
}

.drag-chosen {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--k-color-primary) 55%, transparent);
}

.compact .top-level-list,
.compact .product-list {
  gap: 6px;
  padding: 4px 2px 8px;
}

.compact .group-card {
  padding: 6px 8px;
  border-radius: 8px;
}

.compact .group-header {
  gap: 6px;
  min-height: 26px;
}

.compact .group-title {
  gap: 6px;
}

.compact .group-name {
  font-size: 13px;
  font-weight: 600;
}

.compact .group-actions {
  gap: 4px;
}

.compact .group-body {
  margin-top: 6px;
}

.compact .product-card {
  padding: 4px 6px;
  border-radius: 6px;
  gap: 6px;
}

.compact .product-main {
  gap: 6px;
}

.compact .product-name {
  font-size: 13px;
  line-height: 1.2;
}

.compact .product-controls {
  gap: 4px;
}

.compact .product-controls :deep(.el-input-number) {
  width: 112px;
}

.compact .product-controls :deep(.el-input-number .el-input__inner) {
  font-size: 12px;
}

.compact .empty-dropzone {
  padding: 8px;
  font-size: 12px;
}

@media (max-width: 768px) {
  .product-card {
    flex-direction: column;
    align-items: stretch;
  }

  .product-controls {
    justify-content: flex-end;
    flex-wrap: wrap;
  }
}
</style>
