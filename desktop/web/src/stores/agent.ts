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
  needs_confirm?: boolean  // 问答类为 false，不弹确认条
}
/** 引擎业务状态 → 需要用户确认的节点（对应引擎 steps/{n}/advance）。
 *  界面上不再放流程按钮，流程全部由对话推进，这里就是唯一的推进依据。 */
const CONFIRM_FOR_STATUS: Record<string, { step: number; label: string; next: string }> = {
  CP1_PENDING: { step: 2, label: '剧本', next: '定角色' },
  CP2_PENDING: { step: 4, label: '角色形象', next: '拆镜头' },
  CP3_PENDING: { step: 7, label: '这一版画面', next: '导出成片' },
}
/** 每个动作执行前，引擎状态必须先到达的位置（按顺序推进） */
const NEEDED_STATES: Record<string, string[]> = {
  gen_characters: ['CP1_PENDING'],
  // 拆镜头要走到 PLANNED：先确认剧本，再确认角色形象
  gen_shots: ['CP1_PENDING', 'CP2_PENDING'],
  gen_video: ['CP1_PENDING', 'CP2_PENDING'],
  export_video: ['CP1_PENDING', 'CP2_PENDING', 'CP3_PENDING'],
}
/** 动作做完后，界面应该停在第几步（让用户直接看到结果） */
const STEP_AFTER: Record<string, number> = {
  gen_script: 0,
  regen_script: 0,
  write_next_episode: 0,
  gen_characters: 2,
  swap_role_image: 2,
  gen_shots: 4,
  adjust_pacing: 4,
  gen_video: 5,
  export_video: 7,
}
export const useAgentStore = defineStore('agent', () => {
  const messages = ref<ChatMessage[]>([])
  const pendingIntent = ref<Intent | null>(null)
  const streaming = ref('')
  const executing = ref(false)
  /** 等待模型开口（首字还没来）：这段时间必须有反馈，否则界面像没反应 */
  const thinking = ref(false)
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
  /** 把助手的这段话正式落成一条消息（避免自动执行时消息重复/丢失） */
  function flushAssistantMessage(fallback = '我记下了。') {
    messages.value.push({ role: 'agent', text: streaming.value || fallback })
    streaming.value = ''
  }
  async function send(text: string, projectId: string | null) {
    messages.value.push({ role: 'user', text })
    streaming.value = ''
    pendingIntent.value = null
    thinking.value = true
    let replied = false
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
          if (ev.event === 'token') {
            streaming.value += ev.data.t || ''
            thinking.value = false      // 开口了
          }
          else if (ev.event === 'intent') {
            const intent = ev.data as Intent
            // 问答类不产生可执行动作，不弹确认条
            if (intent.needs_confirm !== false) {
              flushAssistantMessage()
              replied = true
              pendingIntent.value = intent
              if ((intent.cost_impact || 0) <= 0) {
                // 不花钱的动作直接做掉：用户说一句就一步到位，不该再多点一次
                await confirm()
              }
            }
          }
        }
      }
      if (!replied) flushAssistantMessage()
      thinking.value = false
      return pendingIntent.value
    } catch {
      // 降级：JSON 版 chat（SSE 不可用时仍能拿到意图；这不是演示，是真接口）
      thinking.value = false
      const r = await engine.api<{ intent: Intent }>('/api/chat', {
        method: 'POST', body: { message: text, project_id: projectId },
      })
      const reply = r?.intent?.confirm || '本地引擎未连接，暂时无法处理，请确认桌面应用已启动。'
      flushAssistantMessage(reply)
      replied = true
      pendingIntent.value = r?.intent || null
      if (pendingIntent.value && (pendingIntent.value.cost_impact || 0) <= 0) {
        await confirm()
      }
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
      /** 执行动作前先把引擎状态推到该动作需要的位置（界面没有流程按钮了） */
      const ensureState = async (): Promise<string> => {
        for (const st of NEEDED_STATES[intent.op] || []) {
          if (project.status !== st) continue
          const target = CONFIRM_FOR_STATUS[st]
          if (!target) continue
          const payload = st === 'CP2_PENDING' ? { selected: [...project.selectedRoles] } : {}
          const ok = await project.confirmStep(target.step, payload)
          if (!ok) return `卡在「${target.label}」这一步：${engine.error || '暂时无法确认'}`
        }
        return ''
      }
      /** 做完后把界面停到结果所在的那一步 */
      const jumpToResult = () => {
        const s = STEP_AFTER[intent.op]
        if (s === undefined) return
        project.goto(s)
      }
      switch (intent.op) {
        case 'confirm_step': {
          // 界面上没有流程按钮了：用户说"确认""可以了"，就由这里推进状态机
          const target = CONFIRM_FOR_STATUS[project.status]
          if (!target) {
            msg = '现在没有需要你确认的步骤，直接说要做什么就行。'
            break
          }
          const payload = project.status === 'CP2_PENDING' ? { selected: [...project.selectedRoles] } : {}
          const ok = await project.confirmStep(target.step, payload)
          if (!ok) {
            msg = engine.error || '这一步暂时无法确认'
            break
          }
          if (target.step === 4) project.locked = true
          msg = `已确认${target.label}，下一步：${target.next}`
          break
        }
        case 'write_next_episode': {
          // 多集项目：一集一集写，省 token
          const written = project.script?.episodes?.length || 0
          const total = Number((project.detail as any)?.episode_count || 1)
          const idx = written + 1
          if (idx > total) {
            msg = `这个项目一共 ${total} 集，已经写完了。想改写可以说「重新生成这一稿」。`
            break
          }
          const r = await project.genScriptStream(project.scriptVer || 1, idx)
          msg = r.ok ? `第 ${idx} 集已写好并保存到本机（共 ${total} 集）` : (r.error || '生成失败')
          break
        }
        case 'gen_script': {
          // 走流式：卡片会实时逐字刷出内容，用户能立刻看到"正在生成"
          project.goto(0)  // 切到第 1 步，让反馈可见
          const r = await project.genScriptStream(project.script ? project.scriptVer + 1 : 1)
          msg = r.ok ? '剧本已生成，见第 1 步' : (r.error || '剧本生成失败')
          break
        }
        case 'gen_characters': {
          const blocked = await ensureState()
          if (blocked) { msg = blocked; break }
          const r = await project.genCharacters(5)
          msg = r.ok ? '定妆图已生成，去第 3 步查看' : (r.error || '定妆图生成失败')
          break
        }
        case 'gen_shots': {
          const blocked = await ensureState()
          if (blocked) { msg = blocked; break }
          const r = await project.genShots(12)
          msg = r.ok ? '镜头已拆分，去第 5 步查看' : (r.error || '镜头拆分失败')
          break
        }
        case 'gen_video': {
          const blocked = await ensureState()
          if (blocked) { msg = blocked; break }
          const r = await gen.start(project.currentId!, 12)
          msg = r.ok ? '已开始生成画面，去第 6 步看进度' : (r.hint || r.error || '无法开始生成')
          break
        }
        case 'export_video': {
          const blocked = await ensureState()
          if (blocked) { msg = blocked; break }
          const work = await project.exportWork()
          msg = work ? '成片已存入本机作品库（带 AI 标识）' : '导出失败：请先完成画面生成'
          break
        }
        case 'regen_script': {
          project.goto(0)
          const r = await project.genScriptStream(project.scriptVer + 1)
          msg = r.ok ? '剧本已重新生成，见第 1 步' : (r.error || '剧本生成失败')
          break
        }
        case 'adjust_pacing': {
          const blocked = await ensureState()
          if (blocked) { msg = blocked; break }
          const r = await project.genShots(12)
          msg = r.ok ? '已重新拆分镜头（节奏调整）' : (r.error || '镜头拆分失败')
          break
        }
        case 'swap_role_image': {
          const blocked = await ensureState()
          if (blocked) { msg = blocked; break }
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
          // 兜底：不该出现在这里（无可执行动作的问答已被 needs_confirm 过滤）。
          // 不再显示 op 代号，也不发假的"已记录"写请求。
          msg = '这个操作暂时无法执行，换一种说法试试 —— 比如「写剧本」「拆镜头」「生成画面」「导出成片」。'
      }
      // 做完后把界面停到结果所在的那一步（失败时也跳过去，让用户看到原因）
      jumpToResult()
    } finally {
      executing.value = false
      pendingIntent.value = null
    }
    messages.value.push({ role: 'agent', text: msg })
    return msg
  }
  return { messages, pendingIntent, streaming, executing, thinking, send, cancel, confirm }
})
