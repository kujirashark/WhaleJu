<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import StepNav from '@/components/work/StepNav.vue'
import StepBody from '@/components/work/StepBody.vue'
import RightPanel from '@/components/work/RightPanel.vue'
import ChatStream from '@/components/work/ChatStream.vue'

// 深链接 / 刷新时从路由参数恢复当前项目，否则生成/对话都会因 currentId 为空而失败
const route = useRoute()
const project = useProjectStore()
const routeId = String(route.params.id || '')
if (routeId && routeId !== 'current' && routeId !== project.currentId) project.currentId = routeId
</script>

<template>
  <main class="view on">
    <div class="bench">
      <StepNav />
      <section class="main" aria-label="工作区">
        <div class="stream"><StepBody /></div>
        <ChatStream />
      </section>
      <RightPanel />
    </div>
  </main>
</template>
