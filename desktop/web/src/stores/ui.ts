import { defineStore } from 'pinia'
import { ref } from 'vue'

/** 全局 UI 状态：主题、toast、弹窗。纯渲染层，不含业务判断。 */
export const useUiStore = defineStore('ui', () => {
  const theme = ref<'dark' | 'light'>('dark')
  const toastMsg = ref('')
  const userMenuOpen = ref(false)
  let toastTimer: ReturnType<typeof setTimeout> | undefined

  function applyTheme() {
    document.documentElement.setAttribute('data-theme', theme.value)
  }
  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    applyTheme()
  }
  /**
   * 轻提示。默认 3.2 秒；错误类应当更久 ——
   * 2.6 秒根本来不及读完，用户只会觉得"莫名其妙闪了一下"。
   */
  function toast(msg: string, ms = 3200) {
    toastMsg.value = msg
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => (toastMsg.value = ''), ms)
  }
  function closeAll() {
    userMenuOpen.value = false
  }

  return { theme, toastMsg, userMenuOpen, applyTheme, toggleTheme, toast, closeAll }
})
