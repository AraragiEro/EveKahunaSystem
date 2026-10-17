# FRONTEND — src_v2/frontend

Vue3 + TypeScript + Element Plus 前端应用。

## 技术栈

- Vue 3 (Composition API) + TypeScript
- Element Plus UI 组件库
- Pinia 状态管理
- Vue Router 路由
- ECharts 图表
- Vite 构建

## 结构

```
src/
├── main.ts              # 入口，注册路由/Pinia/全局组件
├── App.vue              # 根组件
├── http.ts              # Axios HTTP 客户端封装
├── router/              # 路由定义 (Vue Router)
├── stores/              # Pinia 状态 (auth, market, settings...)
├── views/               # 页面级组件 (路由目标)
├── components/          # 可复用组件
├── composables/         # Vue3 组合式函数 (useXxx)
├── api/                 # 后端 API 调用封装
├── services/            # 业务服务层
├── types/               # TypeScript 类型定义
├── utils/               # 工具函数
├── assets/              # 静态资源 (CSS, 图片)
└── docs/                # 前端文档
```

## 命令

```powershell
cd src_v2/frontend
npm install              # 安装依赖
npm run dev              # 开发服务器 (默认 localhost:5173)
npm run build            # 生产构建 (输出到 ../backend/dist/)
npm run lint             # ESLint 检查
npx vue-tsc --noEmit    # TypeScript 类型检查
```

## 关键模式

- **API 代理**: `vite.config.ts` 中配置代理转发到后端 (端口 9527)
- **API 调用**: `src/api/` 统一封装，使用 `http.ts` 的 Axios 实例
- **状态管理**: Pinia store，持久化使用 localStorage/IndexedDB
- **路由守卫**: 认证检查在路由 `beforeEach` 中
- **组件通信**: Composition API (`ref`, `reactive`, `computed`)，父子用 props/emits

## 类型规范

- 类型定义集中在 `src/types/`
- 禁止 `as any`、`@ts-ignore`
- API 响应类型统一定义在 `api/` 目录

## 与后端关系

- 开发时前端独立运行 (Vite dev server: 5173)，通过代理访问后端 API
- 生产构建输出到 `../backend/dist/`，由 Quart 静态文件服务托管
- 认证通过后端设置的 httpOnly Cookie (JWT)
