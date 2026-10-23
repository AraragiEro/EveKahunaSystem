import { ref } from 'vue'
import { defineStore } from 'pinia'

/**
 * 图标轨「钉住」偏好（P2-b）
 * ---------------------------------------------------------------
 * 之前 smallSideBar 只有 `@mouseenter/@mouseleave` 一条展开路径：
 * 触屏没有 hover、键盘够不到、也没有「我想让它一直开着」的办法。
 * 这里只负责**可持久化**的那一半状态（钉住），临时展开
 * （点折叠按钮 / 指针悬停）留在组件里，刷新即失效。
 *
 *   1. 钉住 = 轨道常驻展开，指针移开不收起；
 *   2. 用户选择写 localStorage（kahuna_sidebar_pinned），刷新后保持；
 *   3. 收起（折叠按钮或 Esc）会一并解除钉住 —— 按钮语义是「收起」，
 *      留着 pinned 会让点击看起来没生效。
 *
 * 钉住**不影响内容区宽度**：展开态是浮层覆盖（P2-e），
 * 所以这里不需要、也不允许再往 App.vue 里写 margin-left。
 */

const PINNED_KEY = 'kahuna_sidebar_pinned'

const readStoredPinned = (): boolean => {
  try {
    return localStorage.getItem(PINNED_KEY) === '1'
  } catch {
    // 隐私模式 / localStorage 不可用：当作没钉住
    return false
  }
}

export const useSidebarStore = defineStore('sidebar', () => {
  const pinned = ref(readStoredPinned())

  const setPinned = (next: boolean) => {
    pinned.value = next
    try {
      localStorage.setItem(PINNED_KEY, next ? '1' : '0')
    } catch {
      // 存不进去也不影响本次会话
    }
  }

  const togglePinned = () => setPinned(!pinned.value)

  /**
   * 二级侧栏抽屉（P2-C，只在 ≤1024 生效）
   * ---------------------------------------------------------------
   * 不新建 store、也不新建第二套状态机：这是侧栏状态机的第四个出口
   * （前三个在 smallSideBar：pinned / openedByUser / hovering）。
   *
   * 与 pinned 的分工：
   *   · pinned      = 「跨会话常驻展开」偏好，写 localStorage，刷新后保持；
   *   · drawerOpen  = 「本次打开」的临时态，刷新即关、不持久化。
   *
   * 为什么窄屏抽屉不继承 pinned：一级图标轨钉住（148px 浮层）与二级面板
   * （180/220px 抽屉）在 375px 下同时常驻会把内容区挤到不可用；窄屏默认
   * 收起，用户显式点汉堡才打开，这是「能用」而不是「牢记偏好」的场景。
   */
  const drawerOpen = ref(false)

  const openDrawer = () => {
    drawerOpen.value = true
  }

  const closeDrawer = () => {
    drawerOpen.value = false
  }

  const toggleDrawer = () => {
    drawerOpen.value = !drawerOpen.value
  }

  return {
    pinned,
    setPinned,
    togglePinned,
    drawerOpen,
    openDrawer,
    closeDrawer,
    toggleDrawer,
  }
})
