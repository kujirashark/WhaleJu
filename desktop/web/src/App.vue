<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUiStore } from '@/stores/ui'
import { useProjectStore } from '@/stores/project'
import { engine } from '@/api/engine'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const project = useProjectStore()
const online = ref(false)

const navItems = [
  { path: '/', label: '首页' },
  { path: '/p/current', label: '制作' },
  { path: '/works', label: '作品库' },
  { path: '/settings', label: '设置' },
]

const crumb = computed(() => {
  if (route.name !== 'work') return ''
  const name = project.projects.find((p: any) => p.id === project.currentId)?.name
  return name ? `项目 / <b>${name}</b>` : ''
})

function go(path: string) {
  ui.closeAll()
  // 「制作」导航必须带上当前项目真实 ID，跳 /p/current 会让 currentId 丢失、
  // 生成/对话全部报「没有当前项目」。没有项目时回首页。
  if (path === '/p/current') {
    if (project.currentId) router.push(`/p/${project.currentId}`)
    else router.push('/')
    return
  }
  router.push(path)
}

async function openFolder(kind: 'data' | 'works') {
  ui.userMenuOpen = false
  const dir = await engine.openFolder(kind)
  ui.toast(dir ? `已打开：${dir}` : (kind === 'data' ? '数据文件夹：文档 / 鲸鲨漫剧' : '成片保存在本机作品库文件夹'))
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') ui.closeAll()
}

onMounted(async () => {
  ui.applyTheme()
  await engine.init()
  online.value = engine.online
  window.addEventListener('keydown', onKey)
  document.addEventListener('click', (e) => {
    const t = e.target as HTMLElement
    if (ui.userMenuOpen && !t.closest('.usermenu') && !t.closest('.avatar')) ui.userMenuOpen = false
  })
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <h1 class="sr-only">鲸鲨漫剧制作台：人的一生，八步从剧本到导出</h1>

  <header class="topbar">
    <div class="brand" @click="go('/')" role="button" tabindex="0">
      <svg class="logo" width="27" height="23" viewBox="0 0 48 40" fill="none" aria-hidden="true">
        <path d="M9 27C11 16.5 17 7.5 26 5c3.4-.9 6 .8 6 4.4V27Z" fill="currentColor" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
        <path d="M4 33.5q4-3.5 8.5 0t8.5 0t8.5 0t8.5 0t6.5 0" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>
      </svg>
      <span class="nm">鲸鲨漫剧</span><span class="ver">LOCAL</span>
    </div>
    <div class="crumb" v-html="crumb"></div>
    <nav class="seg" aria-label="页面">
      <button v-for="n in navItems" :key="n.path"
        :class="{ on: n.path === '/' ? route.name === 'home' : n.path === '/p/current' ? route.name === 'work' : route.name === (n.path === '/works' ? 'works' : 'settings') }"
        @click="go(n.path)">{{ n.label }}</button>
    </nav>
    <div class="topbar-r">
      <div class="status"><i></i><span>{{ online ? '本地引擎已连接' : '引擎未连接' }}</span></div>
      <button class="icobtn" @click="ui.toggleTheme()" :aria-label="ui.theme === 'dark' ? '切换浅色模式' : '切换深色模式'" v-html="ui.theme === 'dark'
        ? '<svg width=\'15\' height=\'15\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'currentColor\' stroke-width=\'1.7\' stroke-linecap=\'round\'><circle cx=\'12\' cy=\'12\' r=\'4\'/><path d=\'M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19\'/></svg>'
        : '<svg width=\'15\' height=\'15\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'currentColor\' stroke-width=\'1.7\' stroke-linecap=\'round\' stroke-linejoin=\'round\'><path d=\'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z\'/></svg>'"></button>
      <button class="avatar" @click="ui.userMenuOpen = !ui.userMenuOpen" aria-label="账户菜单" aria-haspopup="true">K</button>
      <div class="usermenu" :class="{ open: ui.userMenuOpen }" role="menu">
        <div class="um-hd">kujirashark · 本地账户</div>
        <button class="um-it" role="menuitem" @click="openFolder('data')">打开本地数据文件夹</button>
        <button class="um-it" role="menuitem" @click="openFolder('works')">打开作品库文件夹</button>
        <button class="um-it" role="menuitem" @click="ui.userMenuOpen = false; ui.toast('缓存已清除，项目和密钥不受影响')">清除本机缓存</button>
        <div class="um-ft">鲸鲨漫剧 v1.0 · LOCAL</div>
      </div>
    </div>
  </header>

  <router-view />


  <!-- 角色形象确认也走聊天窗口（见 stores/agent.ts 的 confirm_step），不再单独弹窗 -->

  <div class="toast" :class="{ show: !!ui.toastMsg }">{{ ui.toastMsg }}</div>
</template>
