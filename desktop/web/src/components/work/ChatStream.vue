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
  const intent = await agent.send(v, project.currentId)
  if (intent?.confirm) ui.toast('有一项改动需要你确认')
}
async function confirm() {
  const text = await agent.confirm()
  ui.toast(text)
}
</script>
<template>
  <div style="display:flex;flex-direction:column;border-top:1px solid var(--line);background:var(--bg2)">
    <!-- 意图确认条（Never 层：未确认不执行） -->
    <div v-if="agent.pendingIntent" class="intent-bar">
      <div class="ib-txt">
        <b>{{ agent.pendingIntent.confirm || '确认执行这一步？' }}</b>
        <span v-if="agent.pendingIntent.cost_impact > 0" class="chip c-wait">约 {{ agent.pendingIntent.cost_impact.toFixed(0) }} 额度</span>
      </div>
      <div class="ib-acts">
        <button class="btn btn-s" :disabled="agent.executing" @click="agent.cancel(); ui.toast('已取消，没有执行任何操作')">取消</button>
        <button class="btn btn-p" :disabled="agent.executing" @click="confirm">确认执行</button>
      </div>
    </div>
    <!-- SSE 流式回显 -->
    <div v-if="agent.streaming" class="stream-line">{{ agent.streaming }}<span class="caret">▍</span></div>
    <div style="display:flex;gap:8px;padding:12px 24px">
      <input v-model="msg" placeholder="直接说哪里要改，比如：第二集节奏太快了" style="flex:1;border-radius:6px;padding:8px 12px;font-size:12.5px;background:var(--panel);color:var(--ink)" aria-label="给助手的留言" @keyup.enter="send">
      <button class="btn btn-p" @click="send">发送</button>
    </div>
  </div>
</template>
<style scoped>
.intent-bar{margin:10px 24px 0;padding:10px 12px;background:var(--accent-soft);border-radius:6px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.ib-txt{font-size:12px;color:var(--ink);display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ib-acts{display:flex;gap:6px;flex-shrink:0}
.stream-line{margin:8px 24px 0;font-size:12px;color:var(--ink2);font-family:var(--font)}
.caret{color:var(--accent);animation:blink .8s steps(2) infinite}
@keyframes blink{50%{opacity:0}}
</style>
