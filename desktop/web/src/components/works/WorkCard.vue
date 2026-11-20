<script setup lang="ts">
import { IMG } from '@/constants'
import { engine } from '@/api/engine'
import { useUiStore } from '@/stores/ui'
defineProps<{
  img: string
  title: string
  meta: string
  duration: string
  episode?: string
}>()
const ui = useUiStore()
function download() {
  engine.openFolder('works').then((dir) => ui.toast(dir ? `已打开作品库文件夹：${dir}` : '成片保存在本机作品库文件夹'))
}
function copyCap(episode?: string) {
  const text = `${episode || '这一集'} · 鲸鲨漫剧。本视频由 AI 生成，内容已按平台要求标识。`
  if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {})
  ui.toast(`${episode || '这一集'}发布文案已复制，含 AI 生成声明`)
}
</script>
<template>
  <div class="workcard">
    <div class="wshot"><img :src="img" :alt="`${title}成片封面`"><span class="wt">{{ duration }}</span><span class="wk">AI 生成</span></div>
    <div class="wi">
      <div class="t">{{ title }}</div>
      <div class="s">{{ meta }}</div>
      <div class="wacts">
        <button class="btn btn-p" @click="download">下载</button>
        <button class="btn btn-s" @click="copyCap(episode)">复制发布文案</button>
        <button class="btn btn-s" @click="ui.toast('正在只重做这一段，其他镜头不动')">再剪一版</button>
      </div>
    </div>
  </div>
</template>
