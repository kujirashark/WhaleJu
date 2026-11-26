import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// Tauri 桌面壳用 file:// 加载，因此必须用相对资源路径 + hash 路由。
// 构建产物直接覆盖 desktop/frontend，Tauri 的 frontendDist 配置无需改动。
export default defineConfig({
  plugins: [vue()],
  base: './',
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: '../frontend',
    emptyOutDir: true,
    assetsDir: 'assets',
    chunkSizeWarningLimit: 1200,
  },
  server: { port: 1420, strictPort: true },
})
