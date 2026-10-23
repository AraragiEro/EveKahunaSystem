<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElTable } from 'element-plus'
import KEmpty from './KEmpty.vue'
import { useTableDensityStore, type TableDensity } from '@/stores/tableDensity'

/**
 * KTable — 统一报表表格
 * ---------------------------------------------------------------
 * 收敛 24 个文件里 43 处各写一遍的 `<el-table>`。底座是既有的全局样式
 * `assets/report-table.css`（`.k-report-table`：无竖线、极淡行分隔、弱化表头），
 * KTable 在它之上只补三件事：
 *   1. **两档密度** —— `density="default"` 52px / `density="compact"` 40px
 *      （由 `--k-row-h` 加减 `--k-space-*` 推导，不写死像素）；
 *      不传 density 时跟随全站偏好（stores/tableDensity），工业类页面默认紧凑；
 *   2. **数字右对齐** —— 列上给 `class-name="k-num"`（或 `num-cell`）即右对齐 +
 *      等宽数字，不必每列手写 `align="right"`；
 *   3. **空状态统一** —— 传 `emptyWhy` 即用 KEmpty（图标 + 一句为什么 + 操作），
 *      也可以直接给 `#empty` 插槽。
 *
 * 列仍然写在调用方（`<el-table-column>` 作为默认插槽进来），所以列序、
 * 冻结列、自定义单元格模板都不变 —— 不允许为了套组件改信息结构。
 */
const props = withDefaults(
  defineProps<{
    /** 数据源 */
    data: unknown[]
    /**
     * 密度：default 52px / compact 40px。
     * 不传（推荐）时跟随全站偏好，工具条上的密度切换立即生效；
     * 弹窗里的小表需要固定紧凑时再显式传 compact。
     */
    density?: TableDensity
    /** 空状态第一句（为什么空）；不传则用 EP 默认的一行文字 */
    emptyWhy?: string
    /** 空状态补充说明 */
    emptyHint?: string
    /** 空状态主操作文案 */
    emptyAction?: string
  }>(),
  { density: undefined, emptyWhy: '', emptyHint: '', emptyAction: '' }
)

const emit = defineEmits<{ (e: 'empty-action'): void }>()

const densityStore = useTableDensityStore()
/** 显式 density 优先，否则跟随全站偏好 */
const effectiveDensity = computed<TableDensity>(() => props.density ?? densityStore.density)

const tableRef = ref<InstanceType<typeof ElTable>>()

defineExpose({
  /** 需要 EP 原生方法（clearSelection / toggleRowSelection …）时用它 */
  tableRef,
  clearSelection: () => tableRef.value?.clearSelection(),
  toggleRowSelection: (...args: Parameters<InstanceType<typeof ElTable>['toggleRowSelection']>) =>
    tableRef.value?.toggleRowSelection(...args),
  // 树形表格展开/收起：industryPlan 的市场树点行依赖它，漏掉会导致点击行时抛 TypeError
  toggleRowExpansion: (...args: Parameters<InstanceType<typeof ElTable>['toggleRowExpansion']>) =>
    tableRef.value?.toggleRowExpansion(...args),
  doLayout: () => tableRef.value?.doLayout(),
})
</script>

<template>
  <el-table
    ref="tableRef"
    v-bind="$attrs"
    :data="data"
    :class="['k-report-table', 'k-table', `k-table--${effectiveDensity}`]"
  >
    <template #empty>
      <slot name="empty">
        <KEmpty
          v-if="emptyWhy"
          :why="emptyWhy"
          :hint="emptyHint"
          :action-text="emptyAction"
          size="sm"
          inline
          @action="emit('empty-action')"
        />
      </slot>
    </template>
    <slot />
  </el-table>
</template>

<style scoped>
.k-table {
  /* 两档密度：52 = 44 + 8 / 40 = 44 - 4，全部由 token 推导 */
  --k-table-row-h: calc(var(--k-row-h) + var(--k-space-2));
  --k-table-cell-x: var(--k-cell-x);
  width: 100%;
}

.k-table--compact {
  --k-table-row-h: calc(var(--k-row-h) - var(--k-space-1));
}

/* 行高：td 的 height 在表格布局里是最小高度，配合垂直居中即为密度 */
.k-table :deep(.el-table__cell) {
  height: var(--k-table-row-h);
  padding-top: 0;
  padding-bottom: 0;
  vertical-align: middle;
}

/* 表头用 --k-head-h，视觉上比数据行更紧，避免表头抢视线 */
.k-table :deep(th.el-table__cell) {
  height: var(--k-head-h);
}

/* ── 数字右对齐 ───────────────────────────────────────────────
   列上加 `class-name="k-num"`（或沿用 report-table 的 `num-cell`）即可；
   调用方已经写了 align="right" 的列也不会被这里的规则反着覆盖。 */
.k-table :deep(th.k-num .cell),
.k-table :deep(thead th.k-num .cell),
.k-table :deep(tbody td.k-num .cell),
.k-table :deep(thead th.num-cell .cell),
.k-table :deep(tbody td.num-cell .cell) {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
}

/* 不锁列的横向滚动：EP 默认 scrollbar-width:none，这里保证看得见（与 report-table 一致） */
.k-table :deep(.el-scrollbar__wrap) {
  scrollbar-width: thin;
}
</style>
