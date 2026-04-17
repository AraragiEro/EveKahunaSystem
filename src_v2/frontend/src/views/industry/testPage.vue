<template>
    <div ref="graphContainer" style="width: 100%; height: 1200px;"></div>
  </template>
  
  <script setup lang="ts">
  import { ref, onMounted, onUnmounted, watch } from 'vue'
  import * as echarts from 'echarts'
  import type { EChartsOption } from 'echarts'
  import { getChartThemeColors, themedTooltip, onThemeTokenChange } from '@/utils/echartsTheme'
  
  const graphContainer = ref<HTMLElement>()
  let chartInstance: echarts.ECharts | null = null
  let cleanupThemeWatcher: (() => void) | null = null
  
  const graphData = ref({
    nodes: [
      { id: '1', name: '蓝图A', category: 'blueprint' },
      { id: '2', name: '材料1', category: 'material' },
      { id: '3', name: '材料2', category: 'material' },
      { id: '4', name: '产物', category: 'product' }
    ],
    links: [
      { source: '1', target: '2' },
      { source: '1', target: '3' },
      { source: '1', target: '4' }
    ]
  })
  
  const initChart = () => {
    if (!graphContainer.value) return
    const c = getChartThemeColors()
    
    chartInstance = echarts.init(graphContainer.value)
    const option: EChartsOption = {
      title: { text: 'EVE 工业制造关系图', textStyle: { color: c.text } },
      tooltip: { ...themedTooltip(c) },
      series: [{
        type: 'graph',
        layout: 'force',
        data: graphData.value.nodes,
        links: graphData.value.links,
        categories: [
          { name: 'blueprint' },
          { name: 'material' },
          { name: 'product' }
        ],
        roam: true,
        label: { show: true, position: 'right', color: c.text },
        force: {
          repulsion: 1000,
          edgeLength: 200
        }
      }]
    }
    chartInstance.setOption(option)
  }
  
  onMounted(() => {
    cleanupThemeWatcher = onThemeTokenChange(() => {
      initChart()
    })
    initChart()
  })

  onUnmounted(() => {
    cleanupThemeWatcher?.()
    cleanupThemeWatcher = null
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
  })
  
  watch(graphData, () => {
    if (chartInstance) initChart()
  }, { deep: true })
  </script>
