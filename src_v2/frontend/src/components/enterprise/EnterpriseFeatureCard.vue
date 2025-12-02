<script setup lang="ts">
import { ElCard } from 'element-plus'

defineProps<{
  title: string
  description: string
}>()
</script>

<template>
  <el-card class="feature-card" shadow="hover">
    <div class="feature-icon">
      <el-icon :size="32"><Star /></el-icon>
    </div>
    <h3 class="feature-title">{{ title }}</h3>
    <p class="feature-description">{{ description }}</p>
  </el-card>
</template>

<script lang="ts">
import { Star } from '@element-plus/icons-vue'

export default {
  components: {
    Star
  }
}
</script>

<style scoped>
.feature-card {
  cursor: pointer;
  transition: all 0.3s;
}

.feature-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.feature-icon {
  text-align: center;
  margin-bottom: 12px;
  color: #409eff;
}

.feature-title {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 600;
  color: #2c3e50;
  text-align: center;
}

.feature-description {
  margin: 0;
  font-size: 14px;
  color: #64748b;
  text-align: center;
  line-height: 1.5;
}
</style>

