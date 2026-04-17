<script setup lang="ts">
import { ref } from 'vue'

const utils = ref([
  {
    name: 'ZKB',
    description: 'KB网',
    icon: 'icon-1',
    url: 'https://zkillboard.com/',
  },
  {
    name: 'SEAT\n小肥猪火锅城',
    description: 'FRT IT系统',
    icon: 'icon-2',
    url: 'https://seat.winterco.org/',
  },
  {
    name: '联盟合同',
    description: '联盟合同',
    icon: 'icon-3',
    url: '/allianceContract',
  }
])

</script>

<template>
  <el-container class="utils-view">
    <el-header class="utils-header">
      <h1>实用工具</h1>
    </el-header>
    <el-main class="utils-main">
      <el-container class="utils-container">
        <a 
          v-for="item in utils" 
          :key="item.name" 
          :href="item.url"
          target="_blank"
          rel="noopener noreferrer"
          class="card-link"
        >
          <el-card class="utils-card">
            <el-icon :size="20" :name="item.icon"></el-icon>
            <h3>{{ item.name }}</h3>
            <p>{{ item.description }}</p>
          </el-card>
        </a>
      </el-container>
    </el-main>
  </el-container>
</template>

<style scoped>
.utils-view {
  height: 100%;
}

/* 布局容器：用于排列实用工具卡片 */
.utils-container {
  padding: 20px; /* 添加内边距，确保内容不紧贴边缘 */
  display: flex; /* 使用 Flexbox 布局来排列子元素 */
  flex-wrap: wrap; /* 当空间不足时允许子元素换行 */
  gap: 20px; /* 设置子元素之间的间隔 */
}

.utils-header {
  background: var(--k-color-surface);
  border-radius: 12px;
  height: 60px;
  border: 1px solid var(--k-color-border);
}

.utils-card {
  width: 200px;
  height: 200px;
  border-radius: 12px;
  background: var(--k-color-surface);
  box-shadow: var(--k-shadow-sm);
  border: 1px solid var(--k-color-border);
  
}

/* 链接样式规则：确保链接无下划线、继承文字颜色，并以块级形式显示，便于布局 */
.card-link {
  text-decoration: none; /* 移除默认的下划线 */
  color: inherit; /* 继承父元素的文字颜色 */
  display: block; /* 设置为块级元素，方便布局调整 */
}

/* 链接悬停样式：在鼠标悬停时依然不显示下划线 */
.card-link:hover {
  text-decoration: none; /* 保持无下划线状态 */
}

/* Theme override */
.utils-view,
.utils-main,
.utils-container,
.utils-card {
  background: var(--k-color-surface) !important;
  border-color: var(--k-color-border) !important;
  color: var(--k-color-text) !important;
}

.utils-card:hover {
  box-shadow: var(--k-shadow-md) !important;
  background: color-mix(in srgb, var(--k-color-primary) 8%, var(--k-color-surface-soft)) !important;
}

.utils-header h1,
.utils-card h3 {
  color: var(--k-color-text) !important;
}

.utils-card p {
  color: var(--k-color-text-secondary) !important;
}

</style>
