<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import WorkCard from '@/components/works/WorkCard.vue'
import { engine } from '@/api/engine'
import { useUiStore } from '@/stores/ui'
const router = useRouter()
const ui = useUiStore()
const works = ref<any[]>([])
const loading = ref(true)
onMounted(async () => {
  const r = await engine.api<{ items: any[] }>('/api/works')
  works.value = r?.items || []
  loading.value = false
})
const size = (n: number) => n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`
function openWorksFolder() {
  engine.openFolder('works').then((d) => ui.toast(d ? `已打开：${d}` : '作品库文件夹未打开'))
}
</script>
<template>
  <main class="view on">
    <div class="home">
      <div class="home-hero">
        <h1>作品库</h1>
        <p>导出的成片都存在这台电脑上。这里只显示真实导出的作品——下载、复制发布文案。每一集都自动带 AI 生成标识。</p>
      </div>
      <div v-if="loading" class="home-note">正在读取本机作品库…</div>
      <div v-else-if="!works.length" class="works-empty">
        <div class="t">作品库还是空的</div>
        <div class="s">完成一部剧的第 8 步导出后，成片会出现在这里。现在没有可下载的内容。</div>
        <button class="btn btn-s" @click="router.push('/')">去新建项目</button>
      </div>
      <div v-else class="works">
        <WorkCard
          v-for="w in works" :key="w.id"
          :workId="w.id"
          :title="w.project_name || '本机成片'"
          :meta="`${size(w.size_bytes || 0)} · ${new Date(w.created_at).toLocaleString('zh-CN')} 导出`"
          :format="w.format"
          :frames="w.frames"
          episode="成片"
        />
      </div>
      <p class="home-note">发布提示：抖音 / 视频号 / B 站都要求勾选“AI 生成内容”，文案里已经写好声明。<button class="btn btn-t" @click="openWorksFolder">打开文件夹</button></p>
    </div>
  </main>
</template>
