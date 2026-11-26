<script setup lang="ts">
import { engine } from '@/api/engine'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{
  img?: string
  title: string
  meta: string
  duration?: string
  episode?: string
  workId?: string
  format?: string
  frames?: number
}>()
const ui = useUiStore()

/**
 * 下载成片：走引擎的只读下载端点，拿到的就是真文件。
 * 之前这里只是"打开作品库文件夹"，用户点完手里还是没有东西。
 */
function download() {
  if (!props.workId) { ui.toast('这件作品缺少编号，无法下载'); return }
  const url = `${engine.base}/api/works/${props.workId}/download?token=${engine.token}`
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
  ui.toast(props.format === 'frames' ? '开始下载画面素材包（zip）' : '开始下载成片')
}

function openFolder() {
  engine.openFolder('works').then((dir) => ui.toast(dir ? `已打开作品库文件夹：${dir}` : '成片保存在本机作品库文件夹'))
}

async function copyCap() {
  if (props.workId) {
    const r = await engine.api<{ caption: string }>(`/api/works/${props.workId}/caption`)
    if (r?.caption && navigator.clipboard) {
      navigator.clipboard.writeText(r.caption).catch(() => {})
      ui.toast('发布文案已复制，含 AI 生成声明')
      return
    }
  }
  const text = `${props.episode || '这一集'} · 鲸鲨漫剧。本视频由 AI 生成，内容已按平台要求标识。`
  if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {})
  ui.toast('发布文案已复制，含 AI 生成声明')
}

function recut() {
  ui.toast('请回到该项目调整后重新生成；这一段不会被单独伪造重做')
}
</script>

<template>
  <div class="workcard">
    <div class="wshot">
      <img v-if="img" :src="img" :alt="`${title}成片封面`">
      <div v-else class="wshot-ph">真实成片</div>
      <span v-if="duration" class="wt">{{ duration }}</span>
      <span class="wk">AI 生成</span>
    </div>
    <div class="wi">
      <div class="t">{{ title }}</div>
      <div class="s">{{ meta }}</div>
      <div v-if="format === 'frames'" class="wacts">
        <span class="wtag">画面素材包 · {{ frames || 0 }} 张（未合成 mp4）</span>
      </div>
      <div class="wacts">
        <button class="btn btn-p" @click="download">{{ format === 'frames' ? '下载素材包' : '下载成片' }}</button>
        <button class="btn btn-s" @click="copyCap">复制发布文案</button>
        <button class="btn btn-s" @click="recut">再剪一版</button>
        <button class="btn btn-s" @click="openFolder">打开文件夹</button>
      </div>
    </div>
  </div>
</template>
