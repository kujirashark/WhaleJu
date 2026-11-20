<script setup lang="ts">
import { useRouter } from 'vue-router'
import WorkCard from '@/components/works/WorkCard.vue'
import { IMG } from '@/constants'
const router = useRouter()
const works = [
  { img: IMG.child, title: '人的一生 · 第 1 集「院子」', meta: '竖屏 1080×1920 · 412 MB · 2026-11-17 导出', duration: '01:12', episode: '第 1 集' },
  { img: IMG.teen, title: '人的一生 · 第 2 集「站台」', meta: '竖屏 1080×1920 · 466 MB · 2026-11-17 导出', duration: '01:26', episode: '第 2 集' },
  { img: IMG.old, title: '人的一生 · 第 3 集「长椅」', meta: '竖屏 1080×1920 · 489 MB · 2026-11-17 导出', duration: '01:31', episode: '第 3 集' },
]
</script>
<template>
  <main class="view on">
    <div class="home">
      <div class="home-hero">
        <h1>作品库</h1>
        <p>导出的成片都存在这台电脑上。下载、复制发布文案，或者再剪一版。每一集都自动带 AI 生成标识和备案材料包。</p>
      </div>
      <div class="works">
        <WorkCard v-for="w in works" :key="w.title" v-bind="w" />
        <div class="workcard empty">
          <div class="wshot ph"></div>
          <div class="wi">
            <div class="t">下一个作品从这里开始</div>
            <div class="s">回首页用一句话新建项目，做完第 8 步就会出现在这里。</div>
            <div class="wacts"><button class="btn btn-s" @click="router.push('/')">去新建</button></div>
          </div>
        </div>
      </div>
      <p class="home-note">发布提示：抖音 / 视频号 / B 站都要求勾选"AI 生成内容"，文案里已经帮你写好了声明。</p>
    </div>
  </main>
</template>
