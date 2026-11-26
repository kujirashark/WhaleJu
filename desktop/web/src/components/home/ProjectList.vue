<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { useUiStore } from '@/stores/ui'

const router = useRouter()
const project = useProjectStore()
const ui = useUiStore()
const confirmingId = ref<string | null>(null)
const trashOpen = ref(false)
const trash = ref<any[]>([])

onMounted(() => project.loadProjects())

async function toggleTrash() {
  trashOpen.value = !trashOpen.value
  if (trashOpen.value) trash.value = await project.loadTrash()
}

async function restoreItem(p: any) {
  const ok = await project.restore(p.id)
  ui.toast(ok ? `「${p.name}」已恢复` : '恢复失败：本地引擎未响应')
  if (ok) trash.value = await project.loadTrash()
}

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
  if (confirmingId.value === p.id) return
  project.currentId = p.id
  project.step = 0
  if (p.status === 'DELIVER') router.push('/works')
  else router.push(`/p/${p.id}`)
}

async function remove(p: any) {
  const ok = await project.remove(p.id)
  confirmingId.value = null
  ui.toast(ok ? `「${p.name}」已移除，可在「已删除」里恢复` : '删除失败：本地引擎未响应')
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
      <!-- 项目删除：内联二次确认，误删可在回收站恢复 -->
      <span class="proj-del" :class="{ confirming: confirmingId === p.id }" role="button" tabindex="0"
        :aria-label="confirmingId === p.id ? '确认删除项目' : '删除项目'"
        @click.stop="confirmingId === p.id ? remove(p) : (confirmingId = p.id)">
        {{ confirmingId === p.id ? '确认删除' : '移除' }}
      </span>
    </div>
    <!-- 回收站：误删可恢复，避免项目一旦失败就只能永远留在列表里 -->
    <div class="trash-head" role="button" tabindex="0" @click="toggleTrash">
      <span>{{ trashOpen ? '▾' : '▸' }} 已删除的项目</span>
      <span class="trash-count">{{ trash.length }}</span>
    </div>
    <div v-if="trashOpen" class="trash-list">
      <div v-if="!trash.length" class="trash-empty">回收站是空的</div>
      <div v-for="p in trash" :key="p.id" class="trash-row">
        <span class="t">{{ p.name }}</span>
        <button class="btn btn-s" @click="restoreItem(p)">恢复</button>
      </div>
    </div>
  </div>
</template>
