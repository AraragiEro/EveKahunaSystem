<script setup lang="ts">
import { onMounted } from 'vue'
import { ElMessage } from 'element-plus'

const closeWindow = () => {
  try {
    window.close()
  } catch (error) {
    console.error('关闭窗口失败', error)
  }
}

onMounted(() => {
  // 显示成功提示
  ElMessage.success('认证成功，窗口将在3秒后自动关闭')
  
  // 3秒后自动关闭窗口
  setTimeout(() => {
    closeWindow()
  }, 3000)
  
  // 如果自动关闭失败，稍后再次提示
  setTimeout(() => {
    if (!window.closed) {
      ElMessage.info('如果窗口未自动关闭，请手动点击关闭按钮')
    }
  }, 3500)
})
</script>

<template>
  <div class="auth-close-container">
    <el-result
      icon="success"
      title="认证成功"
      sub-title="窗口将在3秒钟后自动关闭"
    >
      <template #extra>
        <el-button type="primary" @click="closeWindow">关闭窗口</el-button>
      </template>
    </el-result>
  </div>
</template>

<style scoped>
.auth-close-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 24px);
  width: 100%;
  padding: 20px;
  box-sizing: border-box;
}
</style>
