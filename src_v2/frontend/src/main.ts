import './assets/theme.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
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
app.use(ElementPlus)

const themeStore = useThemeStore(pinia)
themeStore.initTheme()

app.mount('#app')
