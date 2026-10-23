<script setup lang="ts">
import { computed } from 'vue'

/**
 * 资产构成拆解条（仪表盘 hero 右段）
 * ---------------------------------------------------------------
 * 五段 = 钱包 / 订单 / 运行中 / 标记 / 非标记，与 utils/totalAssets 的
 * 总资产口径逐项对齐（不要在这里另起公式：total 由宿主用 calculateTotalAssets 传进来）。
 *
 * 视觉纪律：
 *  1. 五段是同一色相的「明度阶梯」，不承担语义（没有红=坏/绿=好），
 *     避免把「非标记资产」误读成告警；
 *  2. 每段与卡片底色的对比度 ≥ 3:1 —— 浅色底走「主色 → 压暗」、
 *     深色底走「主色 → 提亮」，两套阶梯分别写在本文件的 CSS 变量里
 *     （theme.css 只读，不新增 token）；
 *  3. 极小段给 `--k-space-1` 的最小宽度，避免 0.1% 的段在条上消失。
 */
interface CompositionItem {
  key: string
  label: string
  value: number
}

const props = defineProps<{
  items: CompositionItem[]
  /** 总资产（与 hero 大数字同一个数） */
  total: number
}>()

const formatCompact = (value: number): string => {
  if (!Number.isFinite(value)) return '0'
  const abs = Math.abs(value)
  if (abs >= 1e12) return `${(value / 1e12).toFixed(2)}T`
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1)}K`
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

const segments = computed(() => {
  const total = props.total
  return props.items.map((item, index) => {
    const value = Number.isFinite(item.value) ? Math.max(item.value, 0) : 0
    const pct = total > 0 ? (value / total) * 100 : 0
    return {
      ...item,
      index: index + 1,
      value,
      pct,
      pctText: `${pct.toFixed(pct >= 10 ? 0 : 1)}%`,
      amountText: `${formatCompact(value)} ISK`,
    }
  })
})

const ariaLabel = computed(() =>
  segments.value
    .filter((s) => s.value > 0)
    .map((s) => `${s.label} ${s.pctText}`)
    .join('，'),
)
</script>

<template>
  <section class="composition" aria-label="资产构成拆解">
    <header class="composition__head">
      <h2 class="composition__title">资产构成</h2>
      <span class="composition__total">{{ formatCompact(total) }} ISK</span>
    </header>

    <div class="composition__bar" role="img" :aria-label="`资产构成：${ariaLabel}`">
      <span
        v-for="seg in segments"
        :key="seg.key"
        class="composition__seg"
        :class="`is-lv-${seg.index}`"
        :style="{ width: `max(var(--k-space-1, 4px), ${seg.pct}%)` }"
        :title="`${seg.label}：${seg.amountText}（${seg.pctText}）`"
      >
        <span v-if="seg.pct >= 12" class="composition__seg-label">{{ seg.pctText }}</span>
      </span>
    </div>

    <ul class="composition__legend">
      <li v-for="seg in segments" :key="seg.key" class="composition__legend-item">
        <i class="composition__dot" :class="`is-lv-${seg.index}`" aria-hidden="true" />
        <div class="composition__legend-text">
          <span class="composition__legend-label">{{ seg.label }}</span>
          <span class="composition__legend-amount">{{ seg.amountText }}</span>
        </div>
        <span class="composition__legend-pct">{{ seg.pctText }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
/* 五段明度阶梯：浅色底 → 主色往前压暗，最低一档仍有 ≥ 4:1；深色底 → 主色往白提亮，最低一档 ≥ 5:1。 */
.composition {
  --comp-1: var(--k-color-primary);
  --comp-2: color-mix(in srgb, var(--k-color-primary) 84%, var(--k-color-shade));
  --comp-3: color-mix(in srgb, var(--k-color-primary) 68%, var(--k-color-shade));
  --comp-4: color-mix(in srgb, var(--k-color-primary) 52%, var(--k-color-shade));
  --comp-5: color-mix(in srgb, var(--k-color-primary) 38%, var(--k-color-shade));

  display: flex;
  flex-direction: column;
  gap: var(--k-space-3);
  min-width: 0;
}

html[data-theme='dark'] .composition {
  --comp-1: var(--k-color-primary);
  --comp-2: color-mix(in srgb, var(--k-color-primary) 84%, var(--k-color-tint));
  --comp-3: color-mix(in srgb, var(--k-color-primary) 68%, var(--k-color-tint));
  --comp-4: color-mix(in srgb, var(--k-color-primary) 52%, var(--k-color-tint));
  --comp-5: color-mix(in srgb, var(--k-color-primary) 36%, var(--k-color-tint));
}

.composition__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--k-space-3);
  min-width: 0;
}

.composition__title {
  margin: 0;
  font-size: var(--k-font-sm);
  font-weight: 600;
  color: var(--k-color-text);
}

.composition__total {
  font-size: var(--k-font-xs);
  color: var(--k-color-text-secondary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* 条：五段紧贴，段间留 2px 缝让「对底」关系可辨 */
.composition__bar {
  display: flex;
  align-items: stretch;
  gap: 2px;
  height: 14px;
  border-radius: var(--k-radius-pill);
  overflow: hidden;
  background: var(--k-color-surface-soft);
}

.composition__seg {
  flex: 0 0 auto;
  min-width: var(--k-space-1, 4px);
  border-radius: var(--k-radius-xs);
  transition: filter var(--k-dur-2) var(--k-ease);
  display: flex;
  align-items: center;
  justify-content: center;
}

.composition__seg:hover {
  filter: brightness(1.12);
}

.composition__seg-label {
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
  color: var(--k-color-text-inverse);
  text-shadow: 0 1px 1px color-mix(in srgb, var(--k-color-shade) 55%, transparent);
  font-variant-numeric: tabular-nums;
}

.is-lv-1 { background: var(--comp-1); }
.is-lv-2 { background: var(--comp-2); }
.is-lv-3 { background: var(--comp-3); }
.is-lv-4 { background: var(--comp-4); }
.is-lv-5 { background: var(--comp-5); }

/* 图例：三列网格（5 项排两行），比两列少一行高度，首屏把空间留给任务列表 */
.composition__legend {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--k-space-2) var(--k-space-3);
}

.composition__legend-item {
  display: flex;
  align-items: center;
  gap: var(--k-space-2);
  min-width: 0;
}

.composition__dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: var(--k-radius-pill);
}

.composition__legend-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  flex: 1;
}

.composition__legend-label {
  font-size: var(--k-font-xs);
  color: var(--k-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.composition__legend-amount {
  font-size: var(--k-font-xs);
  font-weight: 600;
  color: var(--k-color-text);
  font-variant-numeric: tabular-nums;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.composition__legend-pct {
  flex: none;
  font-size: var(--k-font-xs);
  color: var(--k-color-text-tertiary);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 767px) {
  .composition__legend {
    grid-template-columns: 1fr;
  }
}
</style>
