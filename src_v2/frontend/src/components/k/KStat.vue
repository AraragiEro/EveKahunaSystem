<script setup lang="ts">
import { computed } from 'vue'

/**
 * KStat — 统一指标块（单个数 + 标签 + 可选环比）
 * ---------------------------------------------------------------
 * 收敛此前 26 个文件里各写一遍的 `.xxx-stat` / `.card-value` / `el-statistic` 组合。
 *
 * P0 数字保护（必须保留，不要改成普通文本）：
 *  1. `font-variant-numeric: tabular-nums` —— 等宽数字，纵向对齐不抖；
 *  2. `min-width: 0` —— flex 子项默认可被内容撑破，归零才能让父级收缩；
 *  3. 溢出策略 —— 单行 `nowrap + ellipsis`，完整值挂 `title`（原生 tooltip），
 *     需要换行时显式传 `wrap`（如中文长标签混排的金额）。
 * 颜色只用 `--k-*` token，深浅色自动切换。
 */
const props = withDefaults(
  defineProps<{
    /** 指标名，例如「收单额」 */
    label: string
    /** 指标值（已格式化的字符串或原始数字） */
    value: string | number | null | undefined
    /** 单位，例如 ISK / % / 单 */
    unit?: string
    /** 指标名下面的补充说明（口径、时间范围） */
    hint?: string
    /** 环比：正数=上升、负数=下降、null=不显示 */
    delta?: number | null
    /** 环比单位，默认 % */
    deltaUnit?: string
    /** 语义色：default 用正文色，其余给关键数字上色 */
    tone?: 'default' | 'primary' | 'success' | 'warning' | 'danger'
    /** 字号档：md 常规 / lg 大数字（仪表盘首屏） */
    size?: 'md' | 'lg'
    /** 数值为空时显示什么 */
    placeholder?: string
    /** 允许数值换行（默认单行 + 省略号） */
    wrap?: boolean
    /** 数值对齐：默认左对齐，right 用于表格上方右对齐的汇总指标 */
    align?: 'left' | 'right' | 'center'
  }>(),
  {
    unit: '',
    hint: '',
    delta: null,
    deltaUnit: '%',
    tone: 'default',
    size: 'md',
    placeholder: '—',
    wrap: false,
    align: 'left',
  }
)

const display = computed(() => {
  const v = props.value
  if (v === null || v === undefined || v === '') return props.placeholder
  return String(v)
})

/** 完整值给 title：溢出被省略时仍能看到全量 */
const fullText = computed(() => [display.value, props.unit].filter(Boolean).join(' '))

const deltaText = computed(() => {
  if (props.delta === null || props.delta === undefined || Number.isNaN(props.delta)) return ''
  const sign = props.delta > 0 ? '+' : ''
  return `${props.delta > 0 ? '▲' : props.delta < 0 ? '▼' : '●'} ${sign}${props.delta}${props.deltaUnit}`
})

const deltaTone = computed(() => {
  if (props.delta === null || props.delta === undefined) return ''
  if (props.delta > 0) return 'is-up'
  if (props.delta < 0) return 'is-down'
  return 'is-flat'
})
</script>

<template>
  <div
    class="k-stat"
    :class="[`k-stat--${size}`, `k-stat--tone-${tone}`, `k-stat--align-${align}`, wrap ? 'k-stat--wrap' : '']"
  >
    <div class="k-stat__label" :title="label">{{ label }}</div>
    <div class="k-stat__value-row">
      <span class="k-stat__value" :title="fullText">{{ display }}</span>
      <span v-if="unit" class="k-stat__unit">{{ unit }}</span>
    </div>
    <div v-if="hint || deltaText" class="k-stat__foot">
      <span v-if="deltaText" class="k-stat__delta" :class="deltaTone">{{ deltaText }}</span>
      <span v-if="hint" class="k-stat__hint" :title="hint">{{ hint }}</span>
    </div>
  </div>
</template>

<style scoped>
.k-stat {
  display: flex;
  flex-direction: column;
  gap: var(--k-space-1);
  /* 数字保护的基石：默认 min-width 是 auto，长数字会把栅格撑破 */
  min-width: 0;
}

.k-stat__label {
  font-size: var(--k-font-xs);
  line-height: 1.4;
  color: var(--k-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.k-stat__value-row {
  display: flex;
  align-items: baseline;
  gap: var(--k-space-1);
  min-width: 0;
}

.k-stat__value {
  font-size: var(--k-font-xl);
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.01em;
  color: var(--k-color-text);
  /* P0 数字保护：等宽数字 + 可收缩 + 溢出省略 */
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.k-stat__unit {
  flex: none;
  font-size: var(--k-font-xs);
  font-weight: 600;
  color: var(--k-color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.k-stat__foot {
  display: flex;
  align-items: baseline;
  gap: var(--k-space-2);
  min-width: 0;
}

.k-stat__delta {
  flex: none;
  font-size: var(--k-font-xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.k-stat__delta.is-up {
  color: var(--k-color-success);
}
.k-stat__delta.is-down {
  color: var(--k-color-danger);
}
.k-stat__delta.is-flat {
  color: var(--k-color-text-secondary);
}

.k-stat__hint {
  min-width: 0;
  font-size: var(--k-font-xs);
  color: var(--k-color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 档位与修饰 ─────────────────────────────────────────────── */
.k-stat--lg .k-stat__value {
  font-size: var(--k-font-hero);
  line-height: 1.1;
}

.k-stat--tone-primary .k-stat__value {
  color: var(--k-color-primary);
}
.k-stat--tone-success .k-stat__value {
  color: var(--k-color-success);
}
.k-stat--tone-warning .k-stat__value {
  color: var(--k-color-warning);
}
.k-stat--tone-danger .k-stat__value {
  color: var(--k-color-danger);
}

.k-stat--align-right {
  align-items: flex-end;
  text-align: right;
}

.k-stat--align-right .k-stat__value-row,
.k-stat--align-right .k-stat__foot {
  justify-content: flex-end;
  max-width: 100%;
}

/* 居中对齐（汇总卡/门户卡）：标签、数值、脚注一起居中 */
.k-stat--align-center {
  align-items: center;
  text-align: center;
}

.k-stat--align-center .k-stat__value-row,
.k-stat--align-center .k-stat__foot {
  justify-content: center;
  max-width: 100%;
}

/* 显式允许换行时才折行（长中文口径说明等） */
.k-stat--wrap .k-stat__value,
.k-stat--wrap .k-stat__label,
.k-stat--wrap .k-stat__hint {
  white-space: normal;
  overflow-wrap: anywhere;
  text-overflow: clip;
}
</style>
