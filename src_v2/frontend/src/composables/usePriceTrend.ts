import { computed, ref, watch } from 'vue'
import { http } from '@/http'

export interface TrendSummary {
    last_avg: number
    wavg: number
    pct: number
    min_low: number
    max_high: number
    spark: number[]
    volume: number
    as_of: string
}

export type TrendState = 'ok' | 'collecting' | 'missing'

interface SummaryResponse {
    data?: Record<string, TrendSummary>
    meta?: { missing?: number[], collecting?: number, as_of?: string }
}

const MAX_RETRY = 3
const RETRY_DELAY = 6000

/**
 * 批量价格趋势：后端一次算好加权均价 / 涨跌 / 迷你序列。
 *
 * 缺失物品由后端统一排入采集（进程内 single-flight），前端只标记「采集中」，
 * 有限次重取即可拿到；不做本地持久缓存（缓存职责在后端 DB / Redis）。
 */
export function usePriceTrendAuto(typeIds: () => number[], days = 30, marketZone: 'jita' | 'frt' = 'jita') {
    const summaries = ref<Record<string, TrendSummary>>({})
    const missing = ref<number[]>([])
    const collecting = ref(0)
    const asOf = ref('')
    const loading = ref(false)
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    const fetchOnce = async (ids: number[]) => {
        const res = await http.post('/enterprise/market/price_trend_summary', {
            type_ids: ids,
            market_zone: marketZone,
            days,
        })
        return (res?.data ?? {}) as SummaryResponse
    }

    const load = async (ids: number[], attempt = 0) => {
        const list = Array.from(new Set(ids.filter(v => Number(v) > 0)))
        if (!list.length) return
        loading.value = true
        try {
            const body = await fetchOnce(list)
            summaries.value = { ...summaries.value, ...(body.data || {}) }
            missing.value = body.meta?.missing || []
            collecting.value = body.meta?.collecting || 0
            asOf.value = body.meta?.as_of || asOf.value

            if (missing.value.length && attempt < MAX_RETRY) {
                if (retryTimer) clearTimeout(retryTimer)
                retryTimer = setTimeout(() => {
                    void load(missing.value, attempt + 1)
                }, RETRY_DELAY)
            }
        } catch (e) {
            console.error('价格趋势摘要获取失败', e)
        } finally {
            loading.value = false
        }
    }

    watch(typeIds, ids => { void load(ids) }, { immediate: true })

    const summaryOf = (typeId: number | string | null | undefined) => summaries.value[String(typeId)] || null

    const stateOf = (typeId: number | string | null | undefined): TrendState => {
        if (summaryOf(typeId)) return 'ok'
        return missing.value.includes(Number(typeId)) ? 'collecting' : 'missing'
    }

    /** 迷你图路径：70x22 viewBox，平均价折线 + 高低带 */
    const sparkPaths = (s: TrendSummary | null) => {
        const W = 70
        const H = 22
        const PAD = 1.5
        const pts = (s?.spark || []).filter(v => Number.isFinite(v) && v > 0)
        if (pts.length < 2) return { line: '', band: '' }
        const lo = Math.min(s?.min_low || Math.min(...pts), Math.min(...pts))
        const hi = Math.max(s?.max_high || Math.max(...pts), Math.max(...pts))
        const span = Math.max(hi - lo, 1)
        const x = (i: number) => PAD + (i * (W - PAD * 2)) / (pts.length - 1)
        const y = (v: number) => H - PAD - ((v - lo) / span) * (H - PAD * 2)
        const line = pts.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(' ')
        const band = `M${PAD},${y(hi).toFixed(2)} L${(W - PAD).toFixed(2)},${y(hi).toFixed(2)} ` +
            `L${(W - PAD).toFixed(2)},${y(lo).toFixed(2)} L${PAD},${y(lo).toFixed(2)} Z`
        return { line, band }
    }

    return {
        summaries,
        missing,
        collecting,
        asOf,
        loading,
        loadedCount: computed(() => Object.keys(summaries.value).length),
        load,
        summaryOf,
        stateOf,
        sparkPaths,
    }
}