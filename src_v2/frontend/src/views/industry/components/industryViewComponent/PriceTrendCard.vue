<template>
    <div class="price-trend-card">
        <header class="pt-head">
            <span class="pt-name">{{ label || '价格趋势' }}</span>
            <span class="pt-market">JITA · {{ days }}天<template v-if="summary?.as_of"> · {{ summary.as_of }}</template></span>
        </header>

        <div v-if="!summary" class="pt-state">数据缺失</div>

        <template v-else>
            <svg class="pt-chart" viewBox="0 0 260 88" preserveAspectRatio="none" role="img">
                <rect x="0" :y="bandTop" width="260" :height="bandHeight" class="pt-band" />
                <path :d="linePath" class="pt-line" />
            </svg>

            <div class="pt-axis">
                <span>低 {{ formatPrice(summary.min_low) }}</span>
                <span>高 {{ formatPrice(summary.max_high) }}</span>
            </div>

            <div class="pt-stats">
                <KStat label="最新均价" :value="formatPrice(summary.last_avg)" />
                <KStat :label="`${days}天均价`" :value="formatPrice(summary.wavg)" />
            </div>

            <div class="pt-advice" :class="adviceClass">{{ adviceText }}</div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import KStat from '@/components/k/KStat.vue'
import type { TrendSummary } from '@/composables/usePriceTrend'

const props = withDefaults(defineProps<{
    summary: TrendSummary | null
    label?: string
    days?: number
}>(), {
    days: 30,
})

const W = 260
const H = 88
const PAD = 6

const points = computed(() => (props.summary?.spark || []).filter(v => Number.isFinite(v) && v > 0))
const minVal = computed(() => props.summary?.min_low || Math.min(...points.value, 0))
const maxVal = computed(() => props.summary?.max_high || Math.max(...points.value, 0))
const span = computed(() => Math.max(maxVal.value - minVal.value, 1))

const yAt = (v: number) => H - PAD - ((v - minVal.value) / span.value) * (H - PAD * 2)

const linePath = computed(() => {
    const list = points.value
    if (list.length < 2) return ''
    return list
        .map((v, i) => {
            const x = PAD + (i * (W - PAD * 2)) / (list.length - 1)
            return `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${yAt(v).toFixed(2)}`
        })
        .join(' ')
})

const bandTop = computed(() => yAt(maxVal.value))
const bandHeight = computed(() => Math.max(1, yAt(minVal.value) - yAt(maxVal.value)))

const adviceClass = computed(() => {
    const pct = props.summary?.pct || 0
    if (pct <= -8) return 'is-good'
    if (pct >= 8) return 'is-warn'
    return 'is-flat'
})

const adviceText = computed(() => {
    const s = props.summary
    if (!s || !s.wavg) return '数据不足，无法给出判断'
    const p = Math.abs(s.pct).toFixed(1)
    if (s.pct <= -8) return `低于${props.days}天均价 ${p}%，当前价格偏低，适合买入`
    if (s.pct >= 8) return `高于${props.days}天均价 ${p}%，当前价格偏高，建议等待回落`
    return `与${props.days}天均价基本持平（${p}%），价格平稳`
})

const formatPrice = (v: number) => {
    if (!v || !Number.isFinite(v)) return '—'
    return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.price-trend-card { display: flex; flex-direction: column; gap: 8px; }
.pt-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.pt-name { font-size: var(--k-font-sm); font-weight: 600; color: var(--k-color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pt-market { flex: 0 0 auto; font-size: var(--k-font-xs); color: var(--k-color-text-secondary); }
.pt-state { padding: 16px 0; text-align: center; font-size: var(--k-font-xs); color: var(--k-color-text-secondary); }
.pt-chart { width: 100%; height: 88px; display: block; }
.pt-band { fill: color-mix(in srgb, var(--k-color-primary) 12%, transparent); }
.pt-line { fill: none; stroke: color-mix(in srgb, var(--k-color-primary) 85%, transparent); stroke-width: 1.6; vector-effect: non-scaling-stroke; }
.pt-axis { display: flex; justify-content: space-between; font-size: var(--k-font-xs); color: var(--k-color-text-secondary); font-variant-numeric: tabular-nums; }
.pt-stats { display: flex; gap: 16px; padding-top: 6px; border-top: 1px solid var(--k-color-border-subtle); }
.pt-advice { font-size: var(--k-font-xs); line-height: 1.5; padding: 6px 8px; border-radius: var(--k-radius-xs); }
.pt-advice.is-good { color: var(--k-color-success); background: color-mix(in srgb, var(--k-color-success) 12%, transparent); }
.pt-advice.is-warn { color: var(--k-color-danger); background: color-mix(in srgb, var(--k-color-danger) 12%, transparent); }
.pt-advice.is-flat { color: var(--k-color-text-secondary); background: color-mix(in srgb, var(--k-color-text-secondary) 10%, transparent); }
</style>