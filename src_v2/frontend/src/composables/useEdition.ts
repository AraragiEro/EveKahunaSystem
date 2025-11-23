/**
 * 版本检测 Composable
 * 用于检测当前应用版本（社区版或企业版）
 */

import { computed } from 'vue'

/**
 * 版本类型
 */
export type Edition = 'community' | 'enterprise'

/**
 * 从环境变量获取当前应用版本
 * 通过 VITE_APP_EDITION 环境变量控制，默认为 'community'
 */
const APP_EDITION: Edition = (import.meta.env.VITE_APP_EDITION as Edition) || 'community'

/**
 * 判断是否为企业版
 */
export const isEnterprise = computed(() => APP_EDITION === 'enterprise')

/**
 * 判断是否为社区版
 */
export const isCommunity = computed(() => APP_EDITION === 'community')

/**
 * 使用版本的 composable
 */
export function useEdition() {
  // 开发模式下输出版本信息
  if (import.meta.env.DEV) {
    console.log(`[版本检测] 当前版本: ${APP_EDITION}`)
  }

  return {
    edition: APP_EDITION,
    isEnterprise: isEnterprise.value,
    isCommunity: isCommunity.value,
  }
}

