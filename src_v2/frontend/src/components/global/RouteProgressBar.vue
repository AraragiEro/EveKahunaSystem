<script setup lang="ts">
/**
 * 顶部路由切换进度条。
 * 只做视觉反馈，不参与任何业务逻辑；状态由 composables/useRouteProgress.ts 维护。
 */
import { routeProgress } from '@/composables/useRouteProgress'

const { visible, progress } = routeProgress
</script>

<template>
  <div v-show="visible" class="route-progress" aria-hidden="true">
    <div class="route-progress__bar" :style="{ width: `${progress}%` }"></div>
  </div>
</template>

<style scoped>
.route-progress {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  z-index: 4000;
  pointer-events: none;
  background-color: transparent;
}

.route-progress__bar {
  height: 100%;
  border-radius: 0 2px 2px 0;
  background: linear-gradient(
    90deg,
    var(--k-color-primary),
    var(--k-color-primary-soft)
  );
  box-shadow: 0 0 8px color-mix(in srgb, var(--k-color-primary) 60%, transparent);
  transition: width 180ms ease-out;
}
</style>
