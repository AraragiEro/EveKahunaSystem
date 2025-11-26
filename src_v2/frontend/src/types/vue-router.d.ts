// Vue Router 类型扩展
// 这个文件用于扩展 vue-router 的 RouteMeta 接口
// 使用全局类型扩展，不会覆盖原始类型定义

import 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    roles?: string[]
    enterpriseOnly?: boolean
  }
}

