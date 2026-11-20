<script setup lang="ts">
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
async function test() {
  await settings.test(props.id)
  ui.toast(settings.probeResults[props.id] || '连接测试完成')
}
</script>
<template>
  <div class="grp">
    <div class="grp-h">{{ title }}<span>{{ desc }}</span></div>
    <div v-for="o in options" :key="o.v" class="ch" :class="{ sel: settings.slots[id] === o.v }" @click="settings.pick(id, o.v)">
      <span class="rad"></span>
      <div><div class="t">{{ o.t }}</div><div class="d">{{ o.d }}</div></div>
      <span class="pr" :class="{ f: o.free }">{{ o.p }}</span>
    </div>
    <div v-if="settings.slots[id] === 'key'" class="keyrow">
      <input type="password" v-model="settings.keyDrafts[id]" :aria-label="`${title} API 密钥`" placeholder="粘贴你的 API 密钥">
      <button class="btn btn-s" @click="test">测试连接</button>
    </div>
    <div v-if="settings.slots[id] === 'key' && settings.probeResults[id]" class="okline">{{ settings.probeResults[id] }}。密钥只存在这台电脑上。</div>
  </div>
</template>
