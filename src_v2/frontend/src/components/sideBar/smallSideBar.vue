<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import logoImg from '@/assets/logo.jpg'

// 定义菜单项类型
interface MenuItem {
  id: number
  icon: string
  label: string
  active: boolean
  route: string
}

// 定义 props
interface Props {
  menuItems: MenuItem[]
}

const props = defineProps<Props>()
const router = useRouter()

// 侧边栏展开状态
const isExpanded = ref(false)

// 切换菜单项激活状态
const toggleActive = (itemId: number) => {
  const targetRoute = props.menuItems.find(item => item.id === itemId)?.route || '/home'
  router.push(targetRoute)
}

// 鼠标进入侧边栏
const handleMouseEnter = () => {
  isExpanded.value = true
}

// 鼠标离开侧边栏
const handleMouseLeave = () => {
  isExpanded.value = false
}

</script>

<template>
<!-- 左侧窄侧边菜单 -->
<el-aside 
  class="sidebar" 
  :class="{ 'expanded': isExpanded }"
  @mouseenter="handleMouseEnter"
  @mouseleave="handleMouseLeave"
>
  <div class="sidebar-header">
    <div class="logo-container">
      <img :src="logoImg" alt="Logo" class="logo" />
    </div>
  </div>
  
  <el-scrollbar class="sidebar-scrollbar">
    <div class="menu-items">
      <div 
        v-for="item in props.menuItems" 
        :key="item.id"
        class="menu-item"
        :class="{ 'active': item.active }"
        @click="toggleActive(item.id)"
      >
        <div class="menu-icon-container">
          <el-icon :size="20">
            <component :is="item.icon" />
          </el-icon>
        </div>
        <div class="menu-title" :class="{ 'show': isExpanded }">
          {{ item.label }}
        </div>
      </div>
    </div>
  </el-scrollbar>
</el-aside>
</template>

<style scoped>
/* 侧边栏样式 */
.sidebar {
  height: 100vh;
  border-radius: 0 10px 10px 0;
  background: linear-gradient(180deg, #2c3e50 0%, #34495e 100%);
  border-right: 1px solid #e1e8ed;
  display: flex;
  flex-direction: column;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
  transition: width 0.3s ease;
  overflow: hidden;
  position: fixed; /* 使用固定定位 */
  left: 0;
  top: 0;
  z-index: 1000; /* 确保在其他内容之上 */
  width: 60px; /* 初始宽度 */
}

.sidebar.expanded {
  width: 140px !important;
}

.sidebar-header {
  padding: 20px 0;
  display: flex;
  justify-content: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.logo-container {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: rgba(245, 221, 221, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
}

.logo-container:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: scale(1.05);
}

.logo {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  object-fit: contain;
}

.sidebar-scrollbar {
  flex: 1;
  padding: 10px 0;
}
 
.menu-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 10px;
}

.menu-item {
  width: 60px;
  height: 60px;
  border-radius: 12px 0 0 12px;
  background: rgba(255, 255, 255, 0.05);
  display: flex;
  align-items: center;
  justify-content: flex-start;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  margin: 0 auto;
  padding: 0 12px;
  overflow: hidden;
}

.sidebar.expanded .menu-item {
  width: 104px;
}

.menu-item:hover { /* 鼠标悬停时，菜单项的背景颜色变为浅灰色，并向上移动2px，同时添加一个阴影效果 */
  background: rgba(255, 255, 255, 0.15);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.menu-item.active { /* 激活状态时，菜单项的背景颜色变为渐变效果，同时添加一个阴影效果 */
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.menu-item:hover .menu-title, /* 鼠标悬停时，菜单项的标题颜色变为白色 */
.menu-item.active .menu-title { /* 激活状态时，菜单项的标题颜色变为白色 */
  color: rgba(255, 255, 255, 1);
}

.menu-item.active::before { /* 激活状态时，菜单项的左侧添加一个渐变效果的边框 */
  content: '';
  position: absolute;
  left: -10px;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 20px;
  background: #667eea;
  border-radius: 0 2px 2px 0;
}

.menu-icon-container {
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.8);
  transition: color 0.3s ease;
  flex-shrink: 0;
}

.menu-title { /* 菜单项的标题 */
  margin-left: 12px;
  color: rgba(255, 255, 255, 0.8);
  font-size: 18px;
  font-weight: 500;
  white-space: nowrap;
  opacity: 0;
  transform: translateX(-10px);
  transition: all 0.3s ease;
}

.menu-title.show { /* 菜单项的标题显示 */
  opacity: 1;
  transform: translateX(0);
}

.menu-item:hover .menu-icon-container { /* 鼠标悬停时，菜单项的图标颜色变为白色 */
  color: rgba(255, 255, 255, 1);
}

.menu-item.active .menu-icon-container {
  color: white;
}

.sidebar-footer {
  padding: 20px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  justify-content: center;
}

/* 为主内容区域添加左边距，避免被侧边栏遮挡 */
:deep(.el-container) {
  margin-left: 80px;
  transition: margin-left 0.3s ease;
}

/* 当侧边栏展开时，主内容区域也需要调整 */
.sidebar.expanded + .el-container {
  margin-left: 200px;
}
</style>
