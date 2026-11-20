<script setup lang="ts">
import { ref } from 'vue'
import { useAgentStore } from '@/stores/agent'
import { useProjectStore } from '@/stores/project'
import { useUiStore } from '@/stores/ui'
const agent = useAgentStore()
const project = useProjectStore()
const ui = useUiStore()
const msg = ref('')
async function send() {
  const v = msg.value.trim()
  if (!v) { ui.toast('先说点什么，比如：第二集太快了'); return }
  msg.value = ''
  const reply = await agent.send(v, project.currentId)
  ui.toast(reply)
}
</script>
<template>
  <div style="display:flex;gap:8px;padding:12px 24px;border-top:1px solid var(--line);background:var(--bg2)">
    <input v-model="msg" placeholder="直接说哪里要改，比如：第二集节奏太快了" style="flex:1;border-radius:6px;padding:8px 12px;font-size:12.5px;background:var(--panel);color:var(--ink)" aria-label="给助手的留言" @keyup.enter="send">
    <button class="btn btn-p" @click="send">发送</button>
  </div>
</template>
