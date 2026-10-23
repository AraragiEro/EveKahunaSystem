import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

/**
 * 表格密度偏好（全站唯一来源）
 * ---------------------------------------------------------------
 * 之前每个页面各写一套：
 *   · industryPlan.vue 的「卡片密度 普通/紧凑」存 industry_plan_card_style_mode；
 *   · 其余页面在 KTable 上硬编码 density="compact"。
 * 同页多张表、跨页之间因此会不一致。这里收敛成一个偏好：
 *
 *   1. 用户在工具条上切换 → 写 localStorage（kahuna_table_density）；
 *   2. 未选择过 → 按页面类型给默认值：工业类 compact，其余 default；
 *   3. KTable 未显式传 density 时读取这里的「生效值」。
 *
 * 显式传 density 的用法（如弹窗内的紧凑小表）仍然优先，不受偏好影响。
 */

export type TableDensity = 'default' | 'compact'

const DENSITY_KEY = 'kahuna_table_density'

/** 工业类页面信息密度高（材料/成本/流程表都在这里），未选择时默认紧凑 */
const INDUSTRY_PATH_PREFIX = '/industry'

const readStoredDensity = (): TableDensity | null => {
  try {
    const stored = localStorage.getItem(DENSITY_KEY)
    return stored === 'compact' || stored === 'default' ? stored : null
  } catch {
    // 隐私模式 / SSR 下 localStorage 不可用：当作没选过，走默认值
    return null
  }
}

export const useTableDensityStore = defineStore('tableDensity', () => {
  /** 用户显式选择；null = 没选过，按页面类型取默认值 */
  const preference = ref<TableDensity | null>(readStoredDensity())

  /** 当前生效的密度：用户选择 > 页面类型默认值 */
  const density = computed<TableDensity>(() => {
    if (preference.value) return preference.value
    const path = typeof window === 'undefined' ? '' : window.location.pathname
    return path.startsWith(INDUSTRY_PATH_PREFIX) ? 'compact' : 'default'
  })

  const setDensity = (next: TableDensity) => {
    preference.value = next
    try {
      localStorage.setItem(DENSITY_KEY, next)
    } catch {
      // 存不进去也不影响本次会话的使用
    }
  }

  /** 清掉用户选择，回到「按页面类型」的默认值 */
  const resetDensity = () => {
    preference.value = null
    try {
      localStorage.removeItem(DENSITY_KEY)
    } catch {
      // 同上
    }
  }

  return {
    preference,
    density,
    setDensity,
    resetDensity,
  }
})
