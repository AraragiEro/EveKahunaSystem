/// <reference types="vite/client" />

// 扩展 Vue Router 类型
declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    roles?: string[]
    enterpriseOnly?: boolean
  }
}
