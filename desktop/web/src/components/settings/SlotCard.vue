<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{
  id: string
  title: string
  desc: string
  options: { v: string; t: string; d: string; p: string; free?: boolean }[]
}>()
const settings = useSettingsStore()
const ui = useUiStore()

const choice = computed(() => settings.slots[props.id] || '')
const draft = computed(() => settings.drafts[props.id])
const server = computed(() => settings.serverSlots[props.id] || {})
const verified = computed(() => !!server.value.verified)

async function onTest() {
  const ok = await settings.test(props.id)
  ui.toast(ok ? '连接测试通过，这个能力已可以使用' : '连接测试未通过，请检查地址、模型和密钥')
}

const isLocal = computed(() => choice.value === 'local')
const needKey = computed(() => choice.value !== 'local')

async function onSave() {
  const ok = await settings.saveOne(props.id)
  if (!ok) { ui.toast(settings.probeResults[props.id] || '保存失败'); return }
  // saveOne 不刷新 server，这里拉一次权威状态再决定提示，避免用旧 verified 误报
  await settings.load()
  ui.toast(verified.value ? '配置已保存，这个能力仍处于已验证可用状态' : '配置已保存，请点「测试连接」验证')
}
// 密钥已保存到本机时显示掩码（服务端只返回 has_credential，绝不回显明文）
const hasSavedKey = computed(() => !!server.value.has_credential)
const keyPlaceholder = computed(() =>
  hasSavedKey.value ? '••••••••  已保存，留空即沿用' : '首次配置请粘贴密钥'
)
</script>

<template>
  <div class="grp">
    <div class="grp-h">{{ title }}<span>{{ desc }}</span></div>
    <div v-for="o in options" :key="o.v" class="ch" :class="{ sel: choice === o.v }" @click="settings.pick(id, o.v); settings.probeResults[id] = ''">
      <span class="rad"></span>
      <div><div class="t">{{ o.t }}</div><div class="d">{{ o.d }}</div></div>
      <span class="pr" :class="{ f: o.free }">{{ o.p }}</span>
    </div>

    <!-- 未选择来源：明确提示，不默认可用 -->
    <div v-if="!choice" class="hint-warn">还没有为「{{ title }}」选来源。不选就无法使用这个能力，开始前会明确告诉你。</div>

    <template v-else>
      <div class="cfgbox">
        <label class="cf">
          <span>服务地址 <em>必填</em></span>
          <input v-model="draft.endpoint" type="url" :placeholder="isLocal ? 'http://127.0.0.1:11434/v1' : 'https://api.example.com/v1'" :aria-label="`${title} 服务地址`">
          <small>{{ isLocal ? '填你本机/内网模型的地址（通常到 /v1 为止）；本机没部署就不能用这一项' : '填 OpenAI 兼容根地址，一般到 /v1 为止；不要带 /models 或 /chat/completions' }}</small>
        </label>
        <label class="cf">
          <span>模型标识 <em>必填</em></span>
          <input v-model="draft.model" type="text" placeholder="如 deepseek-chat / MiniMax-Text-01" :aria-label="`${title} 模型标识`">
        </label>
        <label class="cf" v-if="needKey">
          <span>API 密钥 <em v-if="hasSavedKey" style="color:var(--ink3);font-style:normal">已保存 ••••</em></span>
          <input v-model="draft.credential" type="password" :placeholder="keyPlaceholder" :aria-label="`${title} API 密钥`">
        </label>
        <div class="cf-row">
          <button class="btn btn-s" :disabled="settings.probing[id]" @click="onSave">保存</button>
          <button class="btn btn-p" :disabled="settings.probing[id]" @click="onTest">{{ settings.probing[id] ? '测试中…' : '测试连接' }}</button>
          <span v-if="verified" class="chip c-ok">已验证可用</span>
          <span v-else class="chip c-wait">未验证 · 不能用于生成</span>
        </div>
      </div>
      <div v-if="settings.probeResults[id]" class="okline" :class="{ bad: settings.probeResults[id].includes('失败') || settings.probeResults[id].includes('请') }">{{ settings.probeResults[id] }}</div>
    </template>
  </div>
</template>
