import { createRouter, createWebHashHistory } from 'vue-router'

// Tauri 以 file:// 加载，history 模式会 404，必须用 hash。
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('@/views/HomeView.vue') },
    { path: '/p/:id', name: 'work', component: () => import('@/views/WorkbenchView.vue') },
    { path: '/works', name: 'works', component: () => import('@/views/WorksView.vue') },
    { path: '/settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
  ],
})
