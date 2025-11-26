<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useEdition } from '@/composables/useEdition'
import { ElMessage } from 'element-plus'

const { isEnterprise } = useEdition()

// 确保只在企业版中显示
if (!isEnterprise) {
  ElMessage.error('此功能仅在企业版中可用')
}

const reports = ref([])
const loading = ref(false)

onMounted(() => {
  if (isEnterprise) {
    loadReports()
  }
})

const loadReports = async () => {
  loading.value = true
  try {
    // 这里可以调用企业版 API
    // const res = await http.get('/api/enterprise/reports')
    // const data = await res.json()
    // if (data.code === 200) {
    //   reports.value = data.data
    // }
    await new Promise(resolve => setTimeout(resolve, 500))
  } catch (error) {
    console.error('加载报表失败:', error)
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="enterprise-reports">
    <div class="reports-header">
      <h1>企业版报表</h1>
      <p class="subtitle">自定义报表功能</p>
    </div>

    <div v-loading="loading" class="reports-content">
      <el-card>
        <template #header>
          <span>报表列表</span>
        </template>
        <div class="reports-placeholder">
          <p>企业版报表功能开发中...</p>
          <p>这里将展示自定义报表列表和报表生成功能</p>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.enterprise-reports {
  padding: 24px;
  background: #f5f7fa;
  min-height: 100%;
}

.reports-header {
  margin-bottom: 24px;
}

.reports-header h1 {
  margin: 0 0 8px 0;
  color: #2c3e50;
  font-size: 28px;
  font-weight: 600;
}

.reports-header .subtitle {
  margin: 0;
  color: #64748b;
  font-size: 14px;
}

.reports-placeholder {
  text-align: center;
  padding: 40px;
  color: #64748b;
}
</style>

