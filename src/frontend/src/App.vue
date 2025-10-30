<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import smallSideBar from './components/sideBar/smallSideBar.vue'

const router = useRouter()
const authStore = useAuthStore()

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}

onMounted(async () => {
  // 应用启动时检查认证状态
  await authStore.checkAuth()
})
</script>

<template>
  <div class="kahuna-container">
    <!-- 登录页面不显示主布局 -->
    <router-view v-if="$route.name === 'login'" />
    
    <!-- 主应用布局 -->
    <el-container v-else>
      <!-- 左侧窄侧边菜单 -->
      <smallSideBar />

      <!-- 主内容区域 -->
      <el-container class="main-container">
        <el-header class="main-header">
          <div class="header-content">
            <h2>Kahuna-System</h2>
            <div class="header-actions">
              
              <!-- 用户信息和退出按钮 -->
              <div class="user-info">
                <el-dropdown @command="handleLogout">
                  <span class="user-dropdown">
                    <el-avatar :size="32" :src="authStore.user?.avatar">
                      {{ authStore.user?.username?.charAt(0)?.toUpperCase() }}
                    </el-avatar>
                    <span class="username">{{ authStore.user?.username }}</span>
                    <el-icon><ArrowDown /></el-icon>
                  </span>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="logout">退出登录</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </div>
        </el-header>
        
        <el-main class="main-content">
          <router-view />
        </el-main>
        
        <el-footer class="main-footer">
          <span>© 2024 Kahuna Bot. All rights reserved.</span>
        </el-footer>
      </el-container>
    </el-container>
  </div>
</template>

<style scoped>
.main-container {
  margin-left: 60px;
  transition: margin-left 0.3s ease;
  height: 100vh;
}

.kahuna-container {
  height: 100vh;
  background-color: #f5f7fa;
}

/* 主内容区域样式 */
.main-header {
  background: white;
  border-bottom: 1px solid #e1e8ed;
  padding: 0 24px;
  display: flex;
  align-items: center;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  border-top-left-radius: 12px;
  border-top-right-radius: 12px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.header-content h2 {
  margin: 0;
  color: #2c3e50;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.main-content {
  padding: 12px;
  background: #f3f3f3;
  height: 100px;
}

.content-wrapper {
  background: white;
  border-radius: 12px;
  padding: 32px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.content-wrapper h3 {
  margin: 0 0 16px 0;
  color: #2c3e50;
  font-weight: 600;
}

.content-wrapper p {
  margin: 0;
  color: #64748b;
  line-height: 1.6;
}

.main-footer {
  background: white;
  border-top: 1px solid #e1e8ed;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  font-size: 14px;
  height: 60px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .sidebar {
    width: 60px !important;
  }
  
  .menu-item {
    width: 50px;
    height: 50px;
  }
  
  .main-header {
    padding: 0 16px;
  }
  
  .main-content {
    padding: 16px;
  }
}

.user-info {
  margin-left: 16px;
}

.user-dropdown {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background-color 0.2s;
}

.user-dropdown:hover {
  background-color: #f1f5f9;
}

.username {
  color: #64748b;
  font-size: 14px;
}
</style>
