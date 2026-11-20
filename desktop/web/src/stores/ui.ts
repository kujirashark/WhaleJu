import { defineStore } from 'pinia'
import { ref } from 'vue'
/** 全局 UI 状态：主题、toast、弹窗。纯渲染层，不含业务判断。 */
export const useUiStore = defineStore('ui', () => {
  const theme = ref<'dark' | 'light'>('dark')
  const toastMsg = ref('')
  const payOpen = ref(false)
  const lockOpen = ref(false)
  const userMenuOpen = ref(false)
  let toastTimer: ReturnType<typeof setTimeout> | undefined
  function applyTheme() {
    document.documentElement.setAttribute('data-theme', theme.value)
  }
  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    applyTheme()
  }
  function toast(msg: string) {
    toastMsg.value = msg
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => (toastMsg.value = ''), 2600)
  }
  function closeAll() {
    payOpen.value = false
    lockOpen.value = false
    userMenuOpen.value = false
  }
  return { theme, toastMsg, payOpen, lockOpen, userMenuOpen, applyTheme, toggleTheme, toast, closeAll }
})
