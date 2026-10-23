<script setup lang="ts">
/**
 * 版心容器：把内容限制在 --k-page-max（≥2200 切到 --k-page-max-wide），
 * 并按「视口居中、左侧图标轨计入公式」的口径换算 margin-left。
 *
 * 为什么不是 margin-inline:auto：
 *   auto 只会在父容器内均分，父容器已经被图标轨推右了 60px，
 *   结果左侧留白比右侧少 60px。这里扣掉半个轨道宽度，
 *   让页面盒在 **视口** 上居中（2560 下左右各 160px）。
 *
 * 图标轨宽度恒为收起态的 60px：hover 展开到 148px 是**浮层覆盖**内容，
 * 不参与任何布局计算（P2-e）。所以这里只有一个 --k-rail-w，没有「展开宽度」。
 */
withDefaults(
  defineProps<{
    /** 页面自身已有 padding（如仪表盘/总览的 24px）时设为 true，避免前后叠加成 48px */
    flush?: boolean
    /** 撑满父容器高度：给 marketView / SidebarLayout 这类自己管理滚动的页面用 */
    fill?: boolean
  }>(),
  { flush: false, fill: false },
)
</script>

<template>
  <div class="k-page" :class="{ 'k-page--flush': flush, 'k-page--fill': fill }">
    <slot />
  </div>
</template>

<style>
/* 版心/图标轨刻度。theme.css（C1）已有 --k-page-max / --k-gutter / --k-grid-cols，
   但没有图标轨宽度和 2K 档版心，这里先由布局组件声明，建议后续并回 theme.css。 */
:root {
  /* 图标轨的**布局让位**宽度：只有收起态的 60px。
     hover 展开的 148px 是浮层，不进这里——否则内容区会随 hover 变宽变窄（P2-e 修的就是这个）。 */
  --k-rail-w: 60px;
  --k-page-max-wide: 2240px;
}
</style>

<style scoped>
.k-page {
  box-sizing: border-box;
  --k-page-max-local: var(--k-page-max, 1760px);
  width: min(100%, var(--k-page-max-local));
  /* 父容器已减去图标轨宽度（.main-container 的 margin-left），
     再扣掉半个轨道即为视口居中：(100vw - 版心) / 2。 */
  margin-left: max(
    0px,
    calc((100% - var(--k-page-max-local)) / 2 - var(--k-rail-w, 60px) / 2)
  );
  margin-right: 0;
  padding-inline: var(--k-gutter, 24px);
}

/* 页面自带内边距时只留版心，不再叠加 gutter */
.k-page--flush {
  padding-inline: 0;
}

/* 高度接力：让 height:100% 的自管滚动页面仍能拿到确定高度 */
.k-page--fill {
  height: 100%;
  min-height: 0;
}

/* 2K 档：≥2200 版心提到 2240px（2560 下左右各 160px） */
@media (min-width: 2200px) {
  .k-page {
    --k-page-max-local: var(--k-page-max-wide, 2240px);
  }
}

/* ── P2-C：≤1024 收窄页边距 ──────────────────────────────────────────
   1280 下 24px 的 gutter 还合适（实测内容宽 1188），再窄就占比过大：
   375 下 60px 图标轨 + 两侧各 24px 只剩 267px 可用。
   只改非 flush 页面（flush 的 0 内边距是页面自己的设计，必须保留），
   1024 及以上完全不受影响。 */
@media (max-width: 1024px) {
  .k-page:not(.k-page--flush) {
    padding-inline: var(--k-gutter-narrow, 12px);
  }
}
</style>
