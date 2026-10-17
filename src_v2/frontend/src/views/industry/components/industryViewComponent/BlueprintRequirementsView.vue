<script setup lang="ts">
import type { BlueprintRequirementItem } from '../interfaceType.vue'

const props = defineProps<{
  bpReqData: BlueprintRequirementItem[]
  selectedPlan: string | null
}>()

// Helper to format bpc_details: [{runs:10},{runs:10},{runs:5}] → "2×10, 1×5"
const formatBpcDetails = (details: Array<{runs: number}>): string => {
  if (!details || details.length === 0) return '-'
  const groups: Record<number, number> = {}
  for (const d of details) {
    groups[d.runs] = (groups[d.runs] || 0) + 1
  }
  return Object.entries(groups)
    .sort((a, b) => Number(b[0]) - Number(a[0]))
    .map(([runs, count]) => `${count}×${runs}`)
    .join(', ')
}

// Formatting helper for numbers
const formatAccounting = (value: any): string => {
  if (value === null || value === undefined) return '-'
  const num = Number(value)
  if (isNaN(num)) return String(value)
  return num.toLocaleString('zh-CN')
}

// Copy cell content
const copyCellContent = async (text: string) => {
  try {
    await navigator.clipboard.writeText(String(text))
    // ElMessage.success('已复制')
  } catch {
    // fallback
  }
}

// Tag type mapping
const getTagType = (type: string): string => {
  switch (type) {
    case '舰船': return ''
    case '组件': return 'success'
    case '反应': return 'warning'
    default: return 'info'
  }
}
</script>

<template>
  <el-table
    v-if="bpReqData && bpReqData.length > 0"
    :data="bpReqData"
    :key="`bp-req-table-${selectedPlan || 'default'}`"
    row-key="type_id"
    border
    stripe
    max-height="75vh"
    class="blueprint-req-table"
    style="font-size: 16px;"
    :default-sort="{prop: 'missing_blueprint_type', order: 'descending'}"
  >
    <el-table-column label="icon" width="60">
      <template #default="{ row }">
        <img
          :src="`https://imageserver.eveonline.com/types/${row.type_id}/icon`"
          alt="icon"
          width="40"
          height="40"
          loading="lazy"
          style="object-fit: contain;"
        />
      </template>
    </el-table-column>
    <el-table-column label="物品名称(zh)" prop="type_name_zh" width="280">
      <template #default="{ row }">
        <div
          class="copyable-cell"
          @click="copyCellContent(row.type_name_zh)"
          :title="`点击复制: ${row.type_name_zh || ''}`"
        >
          {{ row.type_name_zh }}
        </div>
      </template>
    </el-table-column>
    <el-table-column label="物品名称(en)" prop="type_name" width="280">
      <template #default="{ row }">
        <div
          class="copyable-cell"
          @click="copyCellContent(row.type_name)"
          :title="`点击复制: ${row.type_name || ''}`"
        >
          {{ row.type_name }}
        </div>
      </template>
    </el-table-column>
    <el-table-column label="类型" prop="missing_blueprint_type" width="100" sortable :filters="[{text:'舰船',value:'舰船'},{text:'组件',value:'组件'},{text:'反应',value:'反应'},{text:'其他',value:'其他'}]" :filter-method="(value: string, row: any) => row.missing_blueprint_type === value">
      <template #default="{ row }">
        <el-tag :type="getTagType(row.missing_blueprint_type)" effect="plain">
          {{ row.missing_blueprint_type }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="缺少BPC数量" prop="bpc_count" width="130" />
    <el-table-column label="每张BPC运行次数" width="180">
      <template #default="{ row }">
        {{ formatBpcDetails(row.bpc_details) }}
      </template>
    </el-table-column>
    <el-table-column label="总运行次数" prop="runs_total" width="130">
      <template #default="{ row }">
        {{ formatAccounting(row.runs_total) }}
      </template>
    </el-table-column>
    <el-table-column label="T2发明源蓝图" min-width="180">
      <template #default="{ row }">
        <span
          v-if="row.tech2_invention_source_bp_type_name"
          class="copyable-cell"
          @click="copyCellContent(row.tech2_invention_source_bp_type_name!)"
          :title="`点击复制: ${row.tech2_invention_source_bp_type_name}`"
        >
          {{ row.tech2_invention_source_bp_type_name }}
        </span>
        <span v-else class="empty-value">-</span>
      </template>
    </el-table-column>
  </el-table>
  <el-empty v-else description="无缺失蓝图" />
</template>

<style scoped>
/* 可点击复制的单元格样式 */
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

.empty-value {
  color: #999;
}
</style>

<style>
.blueprint-req-table {
  width: 100%;
}

[data-theme="dark"] .blueprint-req-table {
  --el-table-bg-color: var(--k-color-bg-secondary, #1a1a2e);
  --el-table-tr-bg-color: var(--k-color-bg-primary, #16213e);
  --el-table-row-hover-bg-color: var(--k-color-bg-hover, #1f3060);
}

[data-theme="dark"] .blueprint-req-table .copyable-cell:hover {
  background-color: rgba(64, 158, 255, 0.2);
  color: #66b1ff;
}
</style>
