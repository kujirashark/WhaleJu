<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
const router = useRouter()
const project = useProjectStore()
onMounted(() => project.loadProjects())
const STEP_LABEL: Record<string, string> = {
  DRAFT: '第 1 步 · 写剧本',
  CP1_PENDING: '第 2 步 · 确认剧本',
  CHARACT: '第 3 步 · 角色形象',
  CP2_PENDING: '第 4 步 · 确认角色形象',
  PLANNED: '第 5 步 · 拆分镜头',
  RUNNING: '第 6 步 · 生成画面',
  CP3_PENDING: '第 7 步 · 看成片',
  DELIVER: '已完成 · 可去作品库',
}
function open(p: any) {
  project.currentId = p.id
  project.step = 0
  if (p.status === 'DELIVER') router.push('/works')
  else router.push(`/p/${p.id}`)
}
const progress = (s: string) => {
  const order = ['DRAFT', 'CP1_PENDING', 'CHARACT', 'CP2_PENDING', 'PLANNED', 'RUNNING', 'CP3_PENDING', 'DELIVER']
  return Math.round((order.indexOf(s) + 1) / order.length * 100)
}
</script>
<template>
  <div class="home-recent">
    <div class="home-sec">我的项目 · {{ project.projects.length }}</div>
    <div v-if="!project.projects.length" class="proj-empty">
      <div class="t">还没有项目</div>
      <div class="s">在上方写一句想法，开始你的第一部剧。</div>
    </div>
    <div v-for="p in project.projects" :key="p.id" class="proj" @click="open(p)" role="button" tabindex="0" :aria-label="`打开项目：${p.name}`">
      <div class="proj-ph"><span>{{ p.name?.slice(0, 1) || '剧' }}</span></div>
      <div class="pi">
        <div class="t">{{ p.name }}</div>
        <div class="s">{{ STEP_LABEL[p.status] || p.status }}</div>
        <div class="pbar2"><i :style="{ width: progress(p.status) + '%' }"></i></div>
      </div>
      <span class="chip" :class="p.status === 'DELIVER' ? 'p-ok' : 'c-run'">{{ p.status === 'DELIVER' ? '已完成' : '进行中' }}</span>
    </div>
  </div>
</template>
