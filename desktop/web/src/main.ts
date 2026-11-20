import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { engine } from './api/engine'
import { useUiStore } from './stores/ui'
import { useWalletStore } from './stores/wallet'
import './styles/app.css'
const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
// 引擎连接：Tauri 走 IPC 拿令牌，浏览器预览走 7420。
// 用 init() 的同一个 Promise，UI 侧 await 后刷新状态，避免竞态。
engine.init().then(async (ok) => {
  const ui = useUiStore()
  const wallet = useWalletStore()
  ui.toast(ok ? '已连接本机引擎，项目和密钥都保存在这台电脑' : (engine.error || '本地引擎未启动，当前为演示模式'))
  if (ok) await wallet.refresh()
})
