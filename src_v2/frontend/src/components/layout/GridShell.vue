<script setup lang="ts">
/**
 * 12 栏栅格壳：列数吃 --k-grid-cols（C1 token，缺省 12），gutter 缺省 --k-gutter。
 * 列跨度用全局工具类 .k-col-1 ~ .k-col-12（槽内容在父作用域，scoped 选不中），
 * 断点行为对齐 Element Plus 的 el-col：lg=6 → 4 列、md=8 → 3 列、sm=12 → 2 列、xs=24 → 1 列。
 */
withDefaults(
  defineProps<{
    /** 覆盖栅格间距（CSS 长度，可传 "0 24px" 这类双值） */
    gap?: string
    /** 撑满父容器高度（给自管滚动的页面用） */
    fill?: boolean
  }>(),
  { gap: 'var(--k-gutter, 24px)', fill: false },
)
</script>

<template>
  <div
    class="k-grid-shell"
    :class="{ 'k-grid-shell--fill': fill }"
    :style="{ '--k-grid-gap': gap }"
  >
    <slot />
  </div>
</template>

<style>
.k-grid-shell {
  display: grid;
  grid-template-columns: repeat(var(--k-grid-cols, 12), minmax(0, 1fr));
  gap: var(--k-grid-gap, var(--k-gutter, 24px));
  min-width: 0;
}

.k-grid-shell > * {
  min-width: 0;
}

.k-grid-shell--fill {
  height: 100%;
  min-height: 0;
}

.k-col-1 { grid-column: span 1; }
.k-col-2 { grid-column: span 2; }
.k-col-3 { grid-column: span 3; }
.k-col-4 { grid-column: span 4; }
.k-col-5 { grid-column: span 5; }
.k-col-6 { grid-column: span 6; }
.k-col-7 { grid-column: span 7; }
.k-col-8 { grid-column: span 8; }
.k-col-9 { grid-column: span 9; }
.k-col-10 { grid-column: span 10; }
.k-col-11 { grid-column: span 11; }
.k-col-12 { grid-column: span 12; }

/* 与 el-col 的 md / sm / xs 档对齐 */
@media (max-width: 1199px) {
  .k-col-3 { grid-column: span 4; }
  .k-col-4 { grid-column: span 6; }
  .k-col-5,
  .k-col-6 { grid-column: span 6; }
  .k-col-7,
  .k-col-8 { grid-column: span 12; }
}

@media (max-width: 991px) {
  .k-col-3,
  .k-col-4 { grid-column: span 6; }
  .k-col-5,
  .k-col-6 { grid-column: span 12; }
}

@media (max-width: 767px) {
  .k-col-3,
  .k-col-4,
  .k-col-5,
  .k-col-6,
  .k-col-7,
  .k-col-8,
  .k-col-9,
  .k-col-10,
  .k-col-11 { grid-column: span 12; }
}
</style>
