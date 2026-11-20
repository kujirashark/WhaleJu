import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'
/** 对话 Agent（设计 §6.5 / §5.3）：SSE 三事件 + 意图确认门。
 *  Never 层：未确认的写操作一律不执行；确认后由前端调对应业务接口。 */
export interface ChatMessage { role: 'user' | 'agent'; text: string }
export interface Intent {
  op: string
  scope: string
  cost_impact: number
  confirm: string
  confirmed: boolean
}
export const useAgentStore = defineStore('agent', () => {
  const messages = ref<ChatMessage[]>([])
  const pendingIntent = ref<Intent | null>(null)
  const streaming = ref('')
  const executing = ref(false)
  function parseSseChunk(block: string): { event: string; data: any } | null {
    const eventLine = block.split('\n').find((l) => l.startsWith('event:'))
    const dataLine = block.split('\n').find((l) => l.startsWith('data:'))
    if (!eventLine || !dataLine) return null
    try {
      return {
        event: eventLine.slice(6).trim(),
        data: JSON.parse(dataLine.slice(5).trim()),
      }
    } catch {
      return null
    }
  }
  async function send(text: string, projectId: string | null) {
    messages.value.push({ role: 'user', text })
    streaming.value = ''
    pendingIntent.value = null
    // SSE 端点需要 token 走 query（EventSource 不能自定义 header）
    const url = `${engine.base}/api/chat/stream?token=${encodeURIComponent(engine.token)}`
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Local-Token': engine.token,
        },
        body: JSON.stringify({ message: text, project_id: projectId }),
      })
      if (!res.ok || !res.body) throw new Error(`SSE ${res.status}`)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const blocks = buf.split('\n\n')
        buf = blocks.pop() || ''
        for (const block of blocks) {
          const ev = parseSseChunk(block)
          if (!ev) continue
          if (ev.event === 'token') streaming.value += ev.data.t || ''
          else if (ev.event === 'intent') pendingIntent.value = ev.data as Intent
        }
      }
      messages.value.push({ role: 'agent', text: streaming.value || '我记下了。' })
      streaming.value = ''
      return pendingIntent.value
    } catch {
      // 降级：JSON 版 chat（SSE 不可用时仍能拿到意图；这不是演示，是真接口）
      const r = await engine.api<{ intent: Intent }>('/api/chat', {
        method: 'POST', body: { message: text, project_id: projectId },
      })
      const reply = r?.intent?.confirm || '本地引擎未连接，暂时无法处理，请确认桌面应用已启动。'
      messages.value.push({ role: 'agent', text: reply })
      pendingIntent.value = r?.intent || null
      return pendingIntent.value
    }
  }
  function cancel() { pendingIntent.value = null }
  /** 用户确认后由前端调业务接口执行；未确认绝不调用。 */
  async function confirm(): Promise<string> {
    const intent = pendingIntent.value
    if (!intent) return '没有待确认的操作'
    if (intent.cost_impact > 0) {
      const w = await engine.api<{ balance: number }>('/api/wallet')
      if (w && w.balance < intent.cost_impact) {
        pendingIntent.value = null
        return `额度不足（需要约 ${intent.cost_impact.toFixed(0)}），请先充值`
      }
    }
    executing.value = true
    try {
      const r = await engine.api('/api/agent/execute', {
        method: 'POST',
        body: { ...intent, confirmed: true },
      })
      const msg = r ? `${intent.op} 已执行` : `未能执行：本地引擎未响应，请确认应用已启动`
      messages.value.push({ role: 'agent', text: msg })
      pendingIntent.value = null
      return msg
    } finally {
      executing.value = false
    }
  }
  return { messages, pendingIntent, streaming, executing, send, cancel, confirm }
})
