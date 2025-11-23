import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 全局文档帮助 Store
 * 用于管理文档 Drawer 的打开/关闭状态
 * 任何组件都可以通过 useHelpStore().openHelp() 打开文档
 */
export const useHelpStore = defineStore('help', () => {
  // 文档 Drawer 的显示状态
  const isOpen = ref(false)

  /**
   * 打开文档 Drawer
   */
  const openHelp = () => {
    isOpen.value = true
  }

  /**
   * 关闭文档 Drawer
   */
  const closeHelp = () => {
    isOpen.value = false
  }

  /**
   * 切换文档 Drawer 的显示状态
   */
  const toggleHelp = () => {
    isOpen.value = !isOpen.value
  }

  return {
    isOpen,
    openHelp,
    closeHelp,
    toggleHelp
  }
})

