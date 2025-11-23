<template>
  <div class="forbidden-container">
    <div class="forbidden-content">
      <div class="forbidden-icon">
        <el-icon size="120" color="#f56c6c">
          <Lock />
        </el-icon>
      </div>
      
      <h1 class="forbidden-title">403</h1>
      <h2 class="forbidden-subtitle">访问被拒绝</h2>
      <p class="forbidden-description">
        抱歉，您没有权限访问此页面。请联系管理员获取相应权限。
      </p>
      
      <div class="forbidden-actions">
        <el-button type="primary" @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回上一页
        </el-button>
        <el-button @click="goHome">
          <el-icon><House /></el-icon>
          返回首页
        </el-button>
      </div>
      
      <div class="forbidden-info">
        <p>如果您认为这是一个错误，请联系系统管理员</p>
        <p class="contact-info">
          <el-icon><Message /></el-icon>
          邮箱: admin@kahuna-bot.com
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Lock, ArrowLeft, House, Message } from '@element-plus/icons-vue'

const router = useRouter()

const goBack = () => {
  if (window.history.length > 1) {
    router.go(-1)
  } else {
    router.push('/')
  }
}

const goHome = () => {
  router.push('/')
}
</script>

<style scoped>
.forbidden-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  padding: 20px;
}

.forbidden-content {
  text-align: center;
  background: white;
  border-radius: 20px;
  padding: 60px 40px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
  max-width: 500px;
  width: 100%;
}

.forbidden-icon {
  margin-bottom: 24px;
  animation: bounce 2s infinite;
}

.forbidden-title {
  font-size: 72px;
  font-weight: 700;
  color: #f56c6c;
  margin: 0 0 16px 0;
  text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
}

.forbidden-subtitle {
  font-size: 28px;
  font-weight: 600;
  color: #2c3e50;
  margin: 0 0 16px 0;
}

.forbidden-description {
  font-size: 16px;
  color: #64748b;
  line-height: 1.6;
  margin: 0 0 32px 0;
  max-width: 400px;
  margin-left: auto;
  margin-right: auto;
}

.forbidden-actions {
  display: flex;
  gap: 16px;
  justify-content: center;
  margin-bottom: 32px;
  flex-wrap: wrap;
}

.forbidden-actions .el-button {
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 500;
}

.forbidden-info {
  border-top: 1px solid #e2e8f0;
  padding-top: 24px;
}

.forbidden-info p {
  margin: 8px 0;
  color: #94a3b8;
  font-size: 14px;
}

.contact-info {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #64748b !important;
}

@keyframes bounce {
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
  .forbidden-content {
    padding: 40px 20px;
  }
  
  .forbidden-title {
    font-size: 56px;
  }
  
  .forbidden-subtitle {
    font-size: 24px;
  }
  
  .forbidden-actions {
    flex-direction: column;
    align-items: center;
  }
  
  .forbidden-actions .el-button {
    width: 100%;
    max-width: 200px;
  }
}
</style>
