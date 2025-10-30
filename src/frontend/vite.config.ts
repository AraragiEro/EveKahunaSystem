import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools()
  ],
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
})
