<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useTableDensityStore, type TableDensity } from '@/stores/tableDensity'

/**
 * KTableDensitySwitch — 表格密度切换（全站偏好）
 * ---------------------------------------------------------------
 * 由 KToolbar 的 `density-switch` 开关复用，也允许页面直接放在自己的工具条里
 * （industryPlan 的「卡片密度」就走这里，不再维护第二套 localStorage）。
 * 切换后同页所有未显式指定 density 的 <KTable> 立即跟随。
 */
withDefaults(
  defineProps<{
    /** 显示在控件左侧的文案 */
    label?: string
    /** 控件尺寸，跟随所在工具条 */
    size?: 'small' | 'default'
  }>(),
  { label: '密度', size: 'small' }
)

const densityStore = useTableDensityStore()
const { density } = storeToRefs(densityStore)

const handleChange = (value: string | number | boolean) => {
  densityStore.setDensity(value as TableDensity)
}
</script>

<template>
  <div class="k-density-switch" role="group" :aria-label="`表格${label}切换`">
    <span class="k-density-switch__label" aria-hidden="true">{{ label }}</span>
    <el-radio-group :model-value="density" :size="size" @update:model-value="handleChange">
      <el-radio-button value="default">普通</el-radio-button>
      <el-radio-button value="compact">紧凑</el-radio-button>
    </el-radio-group>
  </div>
</template>

<style scoped>
.k-density-switch {
  display: flex;
  align-items: center;
  gap: var(--k-space-2);
  flex: none;
}

.k-density-switch__label {
  font-size: var(--k-font-xs);
  color: var(--k-color-text-tertiary);
  white-space: nowrap;
}
</style>
