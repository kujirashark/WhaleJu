<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useAgentStore } from '@/stores/agent'
import { useProjectStore } from '@/stores/project'
import { useUiStore } from '@/stores/ui'
const agent = useAgentStore()
const project = useProjectStore()
const ui = useUiStore()
const msg = ref('')
const logEl = ref<HTMLElement | null>(null)
// 新消息到达后自动滚到底部，保证"发送后有反应"可见
watch(() => agent.messages.length, () => {
  nextTick(() => { if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight })
})
// 流式内容增长时同样要跟随，否则长回复的下半截看不到
watch(() => agent.streaming.length, () => {
  nextTick(() => { if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight })
})
async function send() {
  const v = msg.value.trim()
  if (!v) { ui.toast('直接说要做什么，比如：写剧本 / 确认剧本 / 拆镜头 / 生成画面'); return }
  msg.value = ''
  await agent.send(v, project.currentId)
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
    <!-- 对话历史：用户消息 + 助手回复（此前从未渲染，导致"发送后无任何反应"） -->
    <div ref="logEl" class="chat-log">
      <div v-for="(m, i) in agent.messages" :key="i" class="chat-msg" :class="m.role">
        <span class="chat-who">{{ m.role === 'user' ? '你' : '助手' }}</span>
        <span class="chat-text">{{ m.text }}</span>
      </div>
      <!-- 正在回复：流式内容直接排在列表里（和历史消息同一条线） -->
      <div v-if="agent.streaming" class="chat-msg agent">
        <span class="chat-who">助手</span>
        <span class="chat-text">{{ agent.streaming }}<span class="caret">▍</span></span>
      </div>
      <!-- 模型还没开口：明确说在等，别让用户以为没发出去 -->
      <div v-else-if="agent.thinking" class="chat-msg agent">
        <span class="chat-who">助手</span>
        <span class="chat-text chat-thinking"><span class="busy-dot"></span>正在思考…</span>
      </div>
    </div>
    <div style="display:flex;gap:8px;padding:12px 24px">
      <input v-model="msg" placeholder="直接说要做什么，比如：写剧本 / 确认剧本 / 拆镜头 / 生成画面 / 导出成片" style="flex:1;border-radius:6px;padding:8px 12px;font-size:12.5px;background:var(--panel);color:var(--ink)" aria-label="给助手的留言" @keyup.enter="send">
      <button class="btn btn-p" :disabled="agent.thinking" @click="send">发送</button>
    </div>
  </div>
</template>
<style scoped>
.chat-log{max-height:210px;overflow-y:auto;padding:8px 24px 0;display:flex;flex-direction:column;gap:6px}
.chat-msg{display:flex;gap:8px;align-items:flex-start;font-size:12px;line-height:1.5}
.chat-who{flex-shrink:0;color:var(--ink3);font-family:var(--mono);font-size:10px;padding-top:1px}
.chat-msg.user .chat-who{color:var(--accent)}
.chat-text{color:var(--ink2);word-break:break-word;white-space:pre-wrap}
.chat-msg.user .chat-text{color:var(--ink)}
.chat-thinking{display:inline-flex;align-items:center;gap:7px;color:var(--ink3)}
.chat-thinking .busy-dot{margin-top:0}
.intent-bar{margin:10px 24px 0;padding:10px 12px;background:var(--accent-soft);border-radius:6px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.ib-txt{font-size:12px;color:var(--ink);display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ib-acts{display:flex;gap:6px;flex-shrink:0}
.caret{color:var(--accent);animation:blink .8s steps(2) infinite}
@keyframes blink{50%{opacity:0}}
</style>
