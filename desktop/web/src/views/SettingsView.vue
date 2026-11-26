<script setup lang="ts">
import { onMounted } from 'vue'
import SlotCard from '@/components/settings/SlotCard.vue'
import { useSettingsStore } from '@/stores/settings'
import { useUiStore } from '@/stores/ui'
const settings = useSettingsStore()
const ui = useUiStore()
// 每项都必须自己配置：不再假定本地已部署模型，也不假定任何默认可用。
// 来源只有两种：自带密钥（owned）与本机模型（local）。纯开源版无平台代采。
const groups = [
  { id: 'text', title: '写剧本、拆分镜头', desc: '第一步', options: [
    { v: 'key', t: '用我自己的 API 密钥', d: '填地址+密钥+模型，直接用自己的账号', p: '推荐' },
    { v: 'local', t: '在你电脑上运行', d: '需自行部署 Ollama 等并填地址', p: '本机自负' },
  ] },
  { id: 'image', title: '生成图片', desc: '决定长相和画风', options: [
    { v: 'key', t: '用我自己的 API 密钥', d: '填地址+密钥+模型', p: '推荐' },
    { v: 'local', t: '在你电脑上运行', d: '需自行部署 ComfyUI 并填地址', p: '本机自负' },
  ] },
  { id: 'video', title: '生成视频', desc: '最花钱的一步', options: [
    { v: 'key', t: '用我自己的 API 密钥', d: '填地址+密钥+模型（要填视频模型名）', p: '推荐' },
    { v: 'local', t: '在你电脑上运行', d: '需自行部署视频模型并填地址', p: '本机自负' },
  ] },
  { id: 'speech', title: '配音', desc: '男女声自动分轨', options: [
    { v: 'key', t: '用我自己的 API 密钥', d: '填地址+密钥+模型', p: '推荐' },
    { v: 'local', t: '在你电脑上运行', d: '需自行部署 TTS 并填地址', p: '本机自负' },
  ] },
]
onMounted(() => settings.load())
async function save() {
  const n = await settings.save()
  ui.toast(n ? `已保存 ${n} 项配置，记得逐项点「测试连接」验证后才能用` : '请先选择来源并填好地址')
}
</script>
<template>
  <main class="view on">
    <div class="settings">
      <h1>模型设置</h1>
      <p class="lead">每个能力都要自己配置：填服务地址、模型标识，以及（除本地外）密钥。本机没有部署模型时，选「自己电脑运行」也用不了，请改用云端 API。密钥加密存在本机，素材和调用都不经过我们。</p>
      <SlotCard v-for="g in groups" :key="g.id" v-bind="g" />
      <div class="acts" style="margin-top:18px"><button class="btn btn-p" @click="save">保存设置</button></div>
      <p class="lead" style="margin-top:22px;font-size:12px">只有「测试连接」通过的能力才能用于生成。没配置或没测通的能力，开始前会明确告诉你，不会用假数据假装成功。</p>
      <p class="lead" style="margin-top:10px;font-size:12px">计费口径：本软件免费开源、不做任何收费。生成消耗的是你自己的厂商额度（自带密钥）或本机算力（本地模型）。</p>
      <p class="lead" style="margin-top:10px;font-size:12px">每一项都要填该能力对应的模型：文字模型不能画图，图片模型也不能生成视频。填错了「测试连接」未必测得出来（它只验证地址通不通），但生成时会立刻停下并告诉你原因，不会白跑一遍。</p>
    </div>
  </main>
</template>
