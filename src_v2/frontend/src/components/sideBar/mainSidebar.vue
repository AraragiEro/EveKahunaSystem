<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

interface MenuItem {
  index: number
  label: string
  route: string
  active?: boolean
}

interface Props {
  menuItems?: MenuItem[]
}

const props = withDefaults(defineProps<Props>(), {
  menuItems: () => [{ index: 1, label: '菜单加载错误', route: '' }],
})

const route = useRoute()
const router = useRouter()

const activeRoute = computed(() => route.path)

const goRoute = (target: string) => {
  if (target) router.push(target)
}
</script>

<template>
  <el-menu :default-active="activeRoute" class="custom-menu" :router="false">
    <el-menu-item
      v-for="item in props.menuItems"
      :key="item.index"
      :index="item.route"
      class="menu-item"
      @click="goRoute(item.route)"
    >
      {{ item.label }}
    </el-menu-item>
  </el-menu>
</template>

<style scoped>
.custom-menu {
  --el-menu-bg-color: transparent;
  --el-menu-text-color: var(--k-color-text-secondary);
  --el-menu-active-color: var(--k-color-text);
  border-right: none;
  background: transparent;
  padding: 8px;
}

.menu-item {
  height: 44px;
  border-radius: 10px;
  margin-bottom: 8px;
  transition: all 0.2s ease;
}

.menu-item:hover {
  background: var(--k-color-surface-soft);
  color: var(--k-color-text);
}

.menu-item.is-active {
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--k-color-primary) 20%, transparent) 0%,
    color-mix(in srgb, var(--k-color-primary) 8%, transparent) 100%
  );
  border: 1px solid color-mix(in srgb, var(--k-color-primary) 36%, var(--k-color-border));
  box-shadow: var(--k-shadow-sm);
}
</style>
