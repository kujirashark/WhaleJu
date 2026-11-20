import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'
import { useProjectStore } from './project'
import { useUiStore } from './ui'
import { useGenStore } from './gen'
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
  /** 用户确认后由前端调真实业务接口执行；未确认绝不调用。
   *  设计 §5.3：Agent 只产意图，写操作必须映射到业务接口，不能只回一个假 effects。 */
  async function confirm(): Promise<string> {
    const intent = pendingIntent.value
    if (!intent) return '没有待确认的操作'
    const project = useProjectStore()
    const ui = useUiStore()
    const gen = useGenStore()
    if (!project.currentId && !['route_to_recharge', 'route_to_settings'].includes(intent.op)) {
      pendingIntent.value = null
      const msg = '还没有选中的项目，请先到首页创建或打开一个项目'
      messages.value.push({ role: 'agent', text: msg })
      return msg
    }
    if (intent.cost_impact > 0) {
      const w = await engine.api<{ balance: number }>('/api/wallet')
      if (w && w.balance < intent.cost_impact) {
        pendingIntent.value = null
        const msg = `额度不足（需要约 ${intent.cost_impact.toFixed(0)}），请先充值`
        messages.value.push({ role: 'agent', text: msg })
        return msg
      }
    }
    executing.value = true
    let msg = ''
    try {
      switch (intent.op) {
        case 'gen_script': {
          const r = await project.genScript(project.script ? project.scriptVer + 1 : 1)
          msg = r.ok ? '剧本已由你配置的模型生成' : (r.error || '剧本生成失败')
          break
        }
        case 'gen_characters': {
          const r = await project.genCharacters(5)
          msg = r.ok ? '定妆图已生成，去第 3 步查看' : (r.error || '定妆图生成失败')
          break
        }
        case 'gen_shots': {
          const r = await project.genShots(12)
          msg = r.ok ? '镜头已拆分，去第 5 步查看' : (r.error || '镜头拆分失败')
          break
        }
        case 'gen_video': {
          const r = await gen.start(project.currentId!, 12)
          msg = r.ok ? '已开始生成画面，去第 6 步看进度' : (r.hint || r.error || '无法开始生成')
          break
        }
        case 'export_video': {
          const work = await project.exportWork()
          msg = work ? '成片已存入本机作品库（带 AI 标识）' : '导出失败：请先完成画面生成'
          break
        }
        case 'regen_script': {
          const r = await project.genScript(project.scriptVer + 1)
          msg = r.ok ? '剧本已重新生成' : (r.error || '剧本生成失败')
          break
        }
        case 'adjust_pacing': {
          const r = await project.genShots(12)
          msg = r.ok ? '已重新拆分镜头（节奏调整）' : (r.error || '镜头拆分失败')
          break
        }
        case 'swap_role_image': {
          const r = await project.genCharacters(5)
          msg = r.ok ? '定妆图已重新生成' : (r.error || '定妆图生成失败')
          break
        }
        case 'route_to_recharge':
          ui.payOpen = true
          msg = '已打开充值窗口'
          break
        case 'route_to_settings':
          window.location.hash = '#/settings'
          msg = '已打开设置'
          break
        default:
          // 纯查询/闲聊类意图仍走引擎确认留痕，但不产生副作用
          await engine.api('/api/agent/execute', {
            method: 'POST', body: { ...intent, confirmed: true },
          })
          msg = `${intent.op} 已记录`
      }
    } finally {
      executing.value = false
      pendingIntent.value = null
    }
    messages.value.push({ role: 'agent', text: msg })
    return msg
  }
  return { messages, pendingIntent, streaming, executing, send, cancel, confirm }
})
