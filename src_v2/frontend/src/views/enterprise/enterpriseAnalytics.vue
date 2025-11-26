<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useEdition } from '@/composables/useEdition'
import { ElMessage } from 'element-plus'
import { http } from '@/http'

const { isEnterprise } = useEdition()

// 确保只在企业版中显示
if (!isEnterprise) {
  ElMessage.error('此功能仅在企业版中可用')
}

const analyticsData = ref({
  chartData: [],
  statistics: {}
})

const loading = ref(false)

onMounted(() => {
  if (isEnterprise) {
    loadAnalyticsData()
  }
})

const loadAnalyticsData = async () => {
  loading.value = true
  try {
    const res = await http.get('/api/enterprise/analytics')
    const data = await res.json()
    if (data.code === 200) {
      analyticsData.value = data.data
    }
  } catch (error) {
    console.error('加载分析数据失败:', error)
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="enterprise-analytics">
    <div class="analytics-header">
      <h1>企业版分析</h1>
      <p class="subtitle">高级数据分析功能</p>
    </div>

    <div v-loading="loading" class="analytics-content">
      <el-card>
        <template #header>
          <span>数据分析</span>
        </template>
        <div class="analytics-placeholder">
          <p>企业版分析功能开发中...</p>
          <p>这里将展示高级数据分析图表和统计信息</p>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.enterprise-analytics {
  padding: 24px;
  background: #f5f7fa;
  min-height: 100%;
}

.analytics-header {
  margin-bottom: 24px;
}

.analytics-header h1 {
  margin: 0 0 8px 0;
  color: #2c3e50;
  font-size: 28px;
  font-weight: 600;
}

.analytics-header .subtitle {
  margin: 0;
  color: #64748b;
  font-size: 14px;
}

.analytics-placeholder {
  text-align: center;
  padding: 40px;
  color: #64748b;
}
</style>

