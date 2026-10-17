/**
 * 路由切换进度条状态
 *
 * 目的：本项目后端部署在国内 NAS、经美国 VPS 中转，页面切换需要下载新的路由 chunk，
 * 实测首字节常在 500ms~1.3s。原先切换期间界面完全无反馈，用户会误以为「卡死」。
 * 这里在导航起始就显示一条进度条，让等待变得可见。
 *
 * 注意：必须在 setupAuthGuards 之前注册，
 * 否则 beforeEach 会排在认证守卫之后，导致进度条要等认证通过才出现。
 */

import { ref, readonly } from 'vue'
import type { Router } from 'vue-router'

const visible = ref(false)
const progress = ref(0)

/** 并发导航计数（重定向会连续触发多次 beforeEach） */
let pendingCount = 0
let growTimer: ReturnType<typeof setInterval> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null

function stopGrow(): void {
  if (growTimer !== null) {
    clearInterval(growTimer)
    growTimer = null
  }
}

function start(): void {
  pendingCount += 1
  if (pendingCount > 1) return

  if (hideTimer !== null) {
    clearTimeout(hideTimer)
    hideTimer = null
  }

  visible.value = true
  progress.value = 8

  stopGrow()
  growTimer = setInterval(() => {
    // 越接近 92% 增长越慢，避免长等待时停在 99% 的观感
    const remaining = 92 - progress.value
    progress.value = Math.min(92, progress.value + Math.max(remaining * 0.12, 0.8))
  }, 120)
}

function finish(): void {
  pendingCount = Math.max(0, pendingCount - 1)
  if (pendingCount > 0) return

  stopGrow()
  progress.value = 100
  hideTimer = setTimeout(() => {
    visible.value = false
    progress.value = 0
    hideTimer = null
  }, 240)
}

/**
 * 注册路由进度钩子。需在 setupAuthGuards 之前调用。
 */
export function registerRouteProgress(router: Router): void {
  router.beforeEach(() => {
    start()
    return true
  })

  router.afterEach(() => {
    finish()
  })

  router.onError(() => {
    finish()
  })
}

/** 供进度条组件消费的只读状态 */
export const routeProgress = {
  visible: readonly(visible),
  progress: readonly(progress),
}
