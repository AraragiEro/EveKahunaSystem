<script setup lang="ts">
import KEmpty from '@/components/k/KEmpty.vue'
import KTable from '@/components/k/KTable.vue'
import { flashCopied, createCopyCellClassName } from '@/composables/useCopyCell'
import type { BlueprintRequirementItem } from '../interfaceType.vue'

defineProps<{
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
const formatAccounting = (value: unknown): string => {
  if (value === null || value === undefined) return '-'
  const num = Number(value)
  if (isNaN(num)) return String(value)
  return num.toLocaleString('zh-CN')
}

// Copy cell content
// 可复制列标记（复制成功的高亮由 flashCopied 直接加在 td 上）
const copyCellClassName = createCopyCellClassName(['type_name_zh', 'type_name', 'tech2_invention_source_bp_type_name'])

const copyCellContent = async (text: string, ev?: MouseEvent) => {
  try {
    await navigator.clipboard.writeText(String(text))
    // ElMessage.success('已复制')
        flashCopied(ev)
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
// footer 汇总：BPC 数量 / 总运行次数
const bpSummary = ({ columns, data }: { columns: Array<{ property?: string }>, data: Array<Record<string, unknown>> }) => {
    return columns.map((col, index: number) => {
        if (index === 0) return '合计'
        const prop = col.property
        if (prop !== 'bpc_count' && prop !== 'runs_total') return ''
        const total = (data || []).reduce((s: number, row: Record<string, unknown>) => s + (Number(row?.[prop]) || 0), 0)
        return total.toLocaleString('zh-CN')
    })
}
</script>

<template>
  <KTable :cell-class-name="copyCellClassName"
    v-if="bpReqData && bpReqData.length > 0"
    density="compact"
    :data="bpReqData"
    :key="`bp-req-table-${selectedPlan || 'default'}`"
    row-key="type_id"
    show-summary
    :summary-method="bpSummary"

    stripe
    height="100%"
    class="blueprint-req-table k-report-table"
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
          @click="copyCellContent(row.type_name_zh, $event)"
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
          @click="copyCellContent(row.type_name, $event)"
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
    <el-table-column label="缺少BPC数量" prop="bpc_count" width="130" align="right" sortable="custom" />
    <el-table-column label="每张BPC运行次数" width="180" align="right">
      <template #default="{ row }">
        {{ formatBpcDetails(row.bpc_details) }}
      </template>
    </el-table-column>
    <el-table-column label="总运行次数" prop="runs_total" width="130" align="right" sortable="custom">
      <template #default="{ row }">
        {{ formatAccounting(row.runs_total) }}
      </template>
    </el-table-column>
    <el-table-column label="T2发明源蓝图" min-width="180">
      <template #default="{ row }">
        <span
          v-if="row.tech2_invention_source_bp_type_name"
          class="copyable-cell"
          @click="copyCellContent(row.tech2_invention_source_bp_type_name!, $event)"
          :title="`点击复制: ${row.tech2_invention_source_bp_type_name}`"
        >
          {{ row.tech2_invention_source_bp_type_name }}
        </span>
        <span v-else class="empty-value">-</span>
      </template>
    </el-table-column>
  </KTable>
  <KEmpty v-else why="无缺失蓝图" hint="当前计划需要的蓝图都已在库存或计划中，不需要额外发明/拷贝" />
</template>

<style scoped>
/* 可点击复制的单元格样式 */
.copyable-cell {
    cursor: pointer;
    user-select: none;
}

.empty-value {
  color: var(--k-color-text-secondary);
}
</style>

<style>
.blueprint-req-table {
  width: 100%;
}

[data-theme="dark"] .blueprint-req-table {
  --el-table-bg-color: var(--k-color-surface);
  --el-table-tr-bg-color: var(--k-color-surface);
  --el-table-row-hover-bg-color: color-mix(in srgb, var(--k-color-primary) 14%, var(--k-color-surface));
}

</style>
