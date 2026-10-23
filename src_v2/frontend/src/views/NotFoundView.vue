<template>
  <div class="not-found-container">
    <div class="not-found-content">
      <div class="not-found-icon">
        <el-icon size="120" color="#f56c6c">
          <Compass />
        </el-icon>
      </div>

      <h1 class="not-found-title">404</h1>
      <h2 class="not-found-subtitle">页面不存在</h2>
      <p class="not-found-description">
        你访问的地址不存在，可能已经改名或移除。请检查链接是否输入正确。
      </p>

      <div class="not-found-actions">
        <el-button type="primary" @click="goHome">
          <el-icon><House /></el-icon>
          回首页
        </el-button>
        <el-button @click="goDashboard">
          <el-icon><DataAnalysis /></el-icon>
          回仪表盘
        </el-button>
      </div>

      <div class="not-found-info">
        <p>如果你认为这是一个错误，请联系系统管理员</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Compass, House, DataAnalysis } from '@element-plus/icons-vue'

const router = useRouter()

const goHome = () => {
  router.push('/')
}

const goDashboard = () => {
  router.push('/dashboard')
}
</script>

<style scoped>
/*
 * 404 兜底页：结构与视觉沿用 ForbiddenView.vue（同为全屏居中卡片 + 跳动图标），
 * 只替换文案与动作入口，避免两套错误页长相不一致。
 */
.not-found-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--k-color-surface-soft) 0%, var(--k-color-surface-strong) 100%);
  padding: 20px;
}

.not-found-content {
  text-align: center;
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  border-radius: 20px;
  padding: 60px 40px;
  box-shadow: var(--k-shadow-md);
  max-width: 500px;
  width: 100%;
}

.not-found-icon {
  margin-bottom: 24px;
  animation: not-found-bounce 2s infinite;
}

.not-found-title {
  font-size: 72px;
  font-weight: 700;
  color: var(--k-color-danger);
  margin: 0 0 16px 0;
  text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
}

.not-found-subtitle {
  font-size: 28px;
  font-weight: 600;
  color: var(--k-color-text);
  margin: 0 0 16px 0;
}

.not-found-description {
  font-size: 16px;
  color: var(--k-color-text-secondary);
  line-height: 1.6;
  margin: 0 0 32px 0;
  max-width: 400px;
  margin-left: auto;
  margin-right: auto;
}

.not-found-actions {
  display: flex;
  gap: 16px;
  justify-content: center;
  margin-bottom: 32px;
  flex-wrap: wrap;
}

.not-found-actions .el-button {
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 500;
}

.not-found-info {
  border-top: 1px solid var(--k-color-border);
  padding-top: 24px;
}

.not-found-info p {
  margin: 8px 0;
  color: var(--k-color-text-tertiary);
  font-size: 14px;
}

@keyframes not-found-bounce {
  0%, 20%, 50%, 80%, 100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-10px);
  }
  60% {
    transform: translateY(-5px);
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .not-found-content {
    padding: 40px 20px;
  }

  .not-found-title {
    font-size: 56px;
  }

  .not-found-subtitle {
    font-size: 24px;
  }

  .not-found-actions {
    flex-direction: column;
    align-items: center;
  }

  .not-found-actions .el-button {
    width: 100%;
    max-width: 200px;
  }
}
</style>
