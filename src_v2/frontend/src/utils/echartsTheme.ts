import type { EChartsOption } from 'echarts'

export interface ChartThemeColors {
  text: string
  textSecondary: string
  border: string
  surface: string
  surfaceSoft: string
  primary: string
  success: string
  warning: string
  danger: string
}

const getCssVar = (name: string, fallback: string) => {
  if (typeof window === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

export const getChartThemeColors = (): ChartThemeColors => ({
  text: getCssVar('--k-color-text', '#303133'),
  textSecondary: getCssVar('--k-color-text-secondary', '#909399'),
  border: getCssVar('--k-color-border', '#dcdfe6'),
  surface: getCssVar('--k-color-surface', '#ffffff'),
  surfaceSoft: getCssVar('--k-color-surface-soft', '#f5f7fa'),
  primary: getCssVar('--k-color-primary', '#409eff'),
  success: getCssVar('--k-color-success', '#67c23a'),
  warning: getCssVar('--k-color-warning', '#e6a23c'),
  danger: getCssVar('--k-color-danger', '#f56c6c')
})

export const themedTooltip = (c: ChartThemeColors): EChartsOption['tooltip'] => ({
  backgroundColor: c.surface,
  borderColor: c.border,
  borderWidth: 1,
  textStyle: {
    color: c.text
  }
})

export const onThemeTokenChange = (callback: () => void) => {
  if (typeof window === 'undefined') {
    return () => {}
  }

  const root = document.documentElement
  const observer = new MutationObserver(() => callback())
  observer.observe(root, {
    attributes: true,
    attributeFilter: ['data-theme', 'style', 'class']
  })

  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const mediaHandler = () => callback()
  media.addEventListener('change', mediaHandler)

  return () => {
    observer.disconnect()
    media.removeEventListener('change', mediaHandler)
  }
}
