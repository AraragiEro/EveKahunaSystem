<script setup lang="ts">
/**
 * KToolbar — 统一操作条（筛选 / 搜索 / 批量操作 / 视图切换）
 * ---------------------------------------------------------------
 * 收敛 23 个文件里各写一遍的 `.filter-section` / `.filter-card` / `.control-panel`
 * / `.toolbar`：左边放查询条件与按钮，右边放视图切换/统计小结。
 *
 * 只负责「一条横条」的排布与外观，不放任何业务逻辑；条件控件由调用方塞进插槽。
 * 深浅色由 `--k-*` token 自动切换。
 *
 * 给 `density-switch` 后，右侧固定出现全站「密度」切换（KTableDensitySwitch）——
 * 带表格的页面只需要开这一个开关，不必各自实现一套。
 */
import KTableDensitySwitch from './KTableDensitySwitch.vue'

withDefaults(
  defineProps<{
    /** 紧凑高度（表格上方常驻时用） */
    dense?: boolean
    /** 描边 + 底色（默认透明，直接坐在页面背景上） */
    bordered?: boolean
    /** 吸顶（长表格滚动时保持操作条可见） */
    sticky?: boolean
    /** 自动换行（条件很多时开，否则不换行） */
    wrap?: boolean
    /** 右侧显示表格密度切换（同页 KTable 立即跟随） */
    densitySwitch?: boolean
    /** 密度切换左侧文案，默认「密度」 */
    densityLabel?: string
  }>(),
  { dense: false, bordered: false, sticky: false, wrap: false, densitySwitch: false, densityLabel: '密度' }
)
</script>

<template>
  <div
    class="k-toolbar"
    :class="[
      dense ? 'k-toolbar--dense' : '',
      bordered ? 'k-toolbar--bordered' : '',
      sticky ? 'k-toolbar--sticky' : '',
      wrap ? 'k-toolbar--wrap' : '',
    ]"
  >
    <div class="k-toolbar__start">
      <slot name="start" />
      <slot />
    </div>
    <div v-if="$slots.end || $slots.actions || densitySwitch" class="k-toolbar__end">
      <slot name="end">
        <slot name="actions" />
      </slot>
      <KTableDensitySwitch v-if="densitySwitch" :label="densityLabel" />
    </div>
  </div>
</template>

<style scoped>
.k-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--k-space-3);
  padding: var(--k-space-3) var(--k-space-4);
  min-width: 0;
}

.k-toolbar--dense {
  padding: var(--k-space-2) var(--k-space-3);
}

.k-toolbar--bordered {
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border-subtle);
  border-radius: var(--k-radius-md);
  box-shadow: var(--k-shadow-xs);
  margin-bottom: var(--k-space-4);
}

.k-toolbar--sticky {
  position: sticky;
  top: 0;
  z-index: var(--k-z-sticky);
  background: var(--k-color-surface);
  border-bottom: 1px solid var(--k-color-border-subtle);
}

.k-toolbar--wrap {
  flex-wrap: wrap;
}

.k-toolbar__start {
  display: flex;
  align-items: center;
  gap: var(--k-space-3);
  min-width: 0;
  flex-wrap: inherit;
}

.k-toolbar__end {
  display: flex;
  align-items: center;
  gap: var(--k-space-2);
  flex: none;
  flex-wrap: inherit;
  margin-left: auto;
}

/* 插槽里的 el-form 行内表单：去掉自带下边距，避免操作条虚高 */
.k-toolbar__start :deep(.el-form--inline .el-form-item),
.k-toolbar__start :deep(.el-form-item) {
  margin-bottom: 0;
  margin-right: var(--k-space-3);
}

.k-toolbar__start :deep(.el-input),
.k-toolbar__start :deep(.el-select) {
  width: auto;
}

/* 窄屏：左右两组改成纵向堆叠，避免操作条被挤成一团 */
@media (max-width: 768px) {
  .k-toolbar,
  .k-toolbar__start,
  .k-toolbar__end {
    flex-direction: column;
    align-items: stretch;
    width: 100%;
  }

  .k-toolbar__end {
    margin-left: 0;
  }
}
</style>
