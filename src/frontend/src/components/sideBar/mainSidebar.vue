<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

// 定义 props
interface MenuItem {
  index: number
  label: string
  route: string
  active?: boolean
}

interface Props {
  menuItems?: MenuItem[]
}

// 定义 props 并设置默认值
const props = withDefaults(defineProps<Props>(), {
  menuItems: () => [
    { index: 1, label: '菜单载入错误', route: ''},
  ]
})

// 切换菜单项激活状态
const toggleActive = (itemId: number) => {
  props.menuItems.forEach(item => {
    item.active = item.index === itemId
  })
  router.push(props.menuItems.find(item => item.index === itemId)?.route || '/')
}

</script>

<template>
<el-menu class="custom-menu">
    <el-menu-item
        v-for="item in menuItems"
        :key="item.index"
        :index="item.index"
        @click="router.push(item.route)"
        class="menu-item"
    >
        {{ item.label }}
    </el-menu-item>
</el-menu>
</template>

<style scoped>
/* 方法1: 通过CSS变量设置菜单项高度 */
.custom-menu {
  --el-menu-item-height: 50px;
  --el-menu-bg-color: #ffffff; /* 菜单背景色 */
  --el-menu-text-color: #303133; /* 文字颜色 */
  --el-menu-active-color: #ffffff; /* 激活状态文字颜色 */
  --el-menu-item-font-size: 18px;

  
  border-radius: 12px;
}

.custom-menu .el-menu-item {
  border-radius: 12px;
  background-color: #ffffff;
  margin-top: 10px;
  transition: all 0.3s ease;
}

.custom-menu .el-menu-item:hover {
  background-color: #e2e2e2;
}

.custom-menu .el-menu-item.is-active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

</style>