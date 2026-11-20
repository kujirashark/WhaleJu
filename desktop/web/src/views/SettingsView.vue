<script setup lang="ts">
import SlotCard from '@/components/settings/SlotCard.vue'
import { useSettingsStore } from '@/stores/settings'
import { useUiStore } from '@/stores/ui'
const settings = useSettingsStore()
const ui = useUiStore()
const groups = [
  { id: 'text', title: '写剧本、拆分镜头', desc: '第一步', options: [
    { v: 'local', t: '在你电脑上运行', d: 'Ollama · Qwen2.5 · 不联网', p: '免费', free: true },
    { v: 'key', t: '用我自己的 API 密钥', d: 'DeepSeek · 可填密钥', p: '约 0.002 元 / 千字' },
    { v: 'plat', t: '用平台额度', d: '不用注册 · 收 12% 手续费', p: '约 0.0023 元 / 千字' },
  ] },
  { id: 'image', title: '生成图片', desc: '决定长相和画风', options: [
    { v: 'key', t: '用我自己的 API 密钥', d: '即梦 · 可填密钥', p: '约 0.20 元 / 张' },
    { v: 'local', t: '在你电脑上运行', d: 'ComfyUI · SDXL', p: '免费', free: true },
    { v: 'plat', t: '用平台额度', d: '不用注册 · 收 15% 手续费', p: '约 0.23 元 / 张' },
  ] },
  { id: 'video', title: '生成视频', desc: '最花钱的一步', options: [
    { v: 'key', t: '用我自己的 API 密钥', d: '可灵 · 重要镜头首选', p: '约 0.45 元 / 条' },
    { v: 'plat', t: '用平台额度（海螺）', d: '过渡镜头首选', p: '约 0.52 元 / 条' },
  ] },
  { id: 'voice', title: '配音', desc: '男女声自动分轨', options: [
    { v: 'local', t: '在你电脑上运行', d: 'edge-tts · 自然度一般', p: '免费', free: true },
    { v: 'plat', t: '用平台额度', d: 'MiniMax 配音 · 更有感情', p: '约 0.10 元 / 千字' },
  ] },
]
async function save() {
  const n = await settings.save()
  ui.toast(n ? `已保存 ${n} 项配置（密钥加密存在本机）` : '设置已保存到本机')
}
</script>
<template>
  <main class="view on">
    <div class="settings">
      <h1>模型设置</h1>
      <p class="lead">每种能力都可以自己选：用平台额度（不用注册就能开始）、填上你自己的密钥（更便宜），或者在你电脑上运行。密钥和素材都不会经过我们。</p>
      <SlotCard v-for="g in groups" :key="g.id" v-bind="g" />
      <div class="acts" style="margin-top:18px"><button class="btn btn-p" @click="save">保存设置</button></div>
      <p class="lead" style="margin-top:22px;font-size:12px">没有设置的能力，在开始之前会明确告诉你，不会直接开始扣钱。</p>
    </div>
  </main>
</template>
