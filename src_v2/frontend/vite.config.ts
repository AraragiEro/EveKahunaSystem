import { fileURLToPath, URL } from 'node:url'

import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// https://vite.dev/config/
export default defineConfig(async ({ command, mode }) => {
  const isDev = command === 'serve' && mode === 'development'
  
  const plugins = [vue()]
  
  // 只在开发服务器模式下动态导入 DevTools
  if (isDev && !process.env.DISABLE_DEVTOOLS) {
    try {
      const vueDevTools = await import('vite-plugin-vue-devtools')
      const devToolsPlugin = vueDevTools.default
      if (devToolsPlugin && typeof devToolsPlugin === 'function') {
        const plugin = devToolsPlugin()
        if (plugin) {
          plugins.push(plugin as Plugin)
        }
      }
    } catch (error) {
      // 忽略错误，继续构建
    }
  }
  
  return {
    plugins,
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      },
    },
    server: {
      proxy: {
        // 所有以 /api 开头的请求，都会被转发到 http://localhost:5000
        '/api': {
          target: 'http://localhost:9527', // 你的Quart后端地址
          changeOrigin: true,
        }
      },
      allowedHosts: [
        'localhost',
        'bottest.setcr-alero.icu',
        'kahubabot.setcr-alero.icu'
      ]
    }
  }
})
