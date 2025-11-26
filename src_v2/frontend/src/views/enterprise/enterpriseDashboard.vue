<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useEdition } from '@/composables/useEdition'
import { ElMessage } from 'element-plus'
import EnterpriseFeatureCard from '@/components/enterprise/EnterpriseFeatureCard.vue'
import { http } from '@/http'

const { isEnterprise } = useEdition()

// 确保只在企业版中显示
if (!isEnterprise) {
  ElMessage.error('此功能仅在企业版中可用')
}

const dashboardData = ref({
  totalUsers: 0,
  activeProjects: 0,
  revenue: 0,
  features: [] as string[]
})

const loading = ref(false)

onMounted(() => {
  if (isEnterprise) {
    loadEnterpriseData()
  }
})

const loadEnterpriseData = async () => {
  loading.value = true
  try {
    const res = await http.get('/api/enterprise/dashboard')
    const data = await res.json()
    if (data.code === 200) {
      dashboardData.value = data.data
    }
  } catch (error) {
    console.error('加载企业版数据失败:', error)
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="enterprise-dashboard">
    <div class="dashboard-header">
      <h1>企业版仪表盘</h1>
      <p class="subtitle">欢迎使用企业版功能</p>
    </div>

    <div v-loading="loading" class="dashboard-content">
      <el-row :gutter="20">
        <el-col :span="6">
          <el-card class="stat-card">
            <div class="stat-value">{{ dashboardData.totalUsers }}</div>
            <div class="stat-label">总用户数</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card class="stat-card">
            <div class="stat-value">{{ dashboardData.activeProjects }}</div>
            <div class="stat-label">活跃项目</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card class="stat-card">
            <div class="stat-value">{{ dashboardData.revenue.toLocaleString() }}</div>
            <div class="stat-label">总收入</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card class="stat-card">
            <div class="stat-value">{{ dashboardData.features.length }}</div>
            <div class="stat-label">可用功能</div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="20" style="margin-top: 20px">
        <el-col :span="24">
          <el-card>
            <template #header>
              <span>企业版功能</span>
            </template>
            <div class="features-list">
              <EnterpriseFeatureCard
                v-for="(feature, index) in dashboardData.features"
                :key="index"
                :title="feature"
                :description="`${feature}功能详情`"
              />
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<style scoped>
.enterprise-dashboard {
  padding: 24px;
  background: #f5f7fa;
  min-height: 100%;
}

.dashboard-header {
  margin-bottom: 24px;
}

.dashboard-header h1 {
  margin: 0 0 8px 0;
  color: #2c3e50;
  font-size: 28px;
  font-weight: 600;
}

.dashboard-header .subtitle {
  margin: 0;
  color: #64748b;
  font-size: 14px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  font-size: 32px;
  font-weight: 600;
  color: #409eff;
  margin-bottom: 8px;
}

.stat-label {
  font-size: 14px;
  color: #64748b;
}

.features-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 16px;
}
</style>

