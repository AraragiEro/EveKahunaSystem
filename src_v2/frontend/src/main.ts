import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

/**
 * ⚠️ CSS 导入顺序不能调换：
 *   1. Element Plus 基础样式（浅色默认值都在 :root 里）
 *   2. Element Plus 官方深色变量（挂在 html.dark 上）
 *   3. 本项目主题 theme.css —— 必须最后导入，否则它里面的 --el-* 桥接规则
 *      会被 EP 的 :root 覆盖（同优先级、后导入者胜），深色模式会出现白输入框 /
 *      白按钮 / 浅灰文字。
 * 参考：docs/ui-audit-2026-10-17/README.md 第 1.1 节
 */
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './assets/theme.css'
/* 报表表格统一外观（.k-report-table），必须在 theme.css 之后 */
import './assets/report-table.css'

import { useThemeStore } from './stores/theme'
import App from './App.vue'
import router from './router'

function loadAdsenseScript() {
  const adsenseEnabled = (import.meta.env.VITE_ENABLE_ADSENSE as string | undefined)?.toLowerCase() === 'true'
  if (!adsenseEnabled) return

  const scriptSrc = import.meta.env.VITE_ADSENSE_SCRIPT_SRC as string | undefined

  if (!scriptSrc) {
    console.warn('[adsense] enabled but no script source configured')
    return
  }

  if (document.querySelector(`script[src="${scriptSrc}"]`)) return

  const script = document.createElement('script')
  script.async = true
  script.src = scriptSrc
  script.crossOrigin = 'anonymous'
  document.head.appendChild(script)
}

loadAdsenseScript()

const app = createApp(App)

// 全局 Vue 错误处理器：捕获未处理的渲染错误
app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue Error]', err, info)
}

const pinia = createPinia()

app.use(pinia)
app.use(router)
// locale 决定组件内置文案（表格空态、日期选择器、分页、上传等），必须显式指定中文
app.use(ElementPlus, { locale: zhCn })

const themeStore = useThemeStore(pinia)
themeStore.initTheme()

app.mount('#app')
