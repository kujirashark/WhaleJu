import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'
/** 对话 Agent：只做意图改写与 pending 确认门；写操作仍走业务接口，由用户确认。 */
export const useAgentStore = defineStore('agent', () => {
  const messages = ref<{ role: 'user' | 'agent'; text: string }[]>([])
  const pendingIntent = ref<any | null>(null)
  async function send(text: string, projectId: string | null) {
    messages.value.push({ role: 'user', text })
    const r = await engine.api<{ intent: any }>('/api/chat', {
      method: 'POST', body: { message: text, project_id: projectId },
    })
    const reply = r?.intent
      ? `我理解你想：${r.intent.confirm || r.intent.op}。这一步需要你确认后才会执行。`
      : '收到。助手会按这句话调整下一稿（演示模式，未连接引擎）。'
    messages.value.push({ role: 'agent', text: reply })
    pendingIntent.value = r?.intent || null
    return reply
  }
  return { messages, pendingIntent, send }
})
