import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { engine } from '@/api/engine'
import { useUiStore } from './ui'
import { useCallsStore } from './calls'
/** 项目与制作流程：状态、步骤、角色选择、生成/播放/导出。
 *  守卫在引擎，前端的 step 只用于界面呈现；所有内容来自引擎真实数据。 */
export const useProjectStore = defineStore('project', () => {
  const currentId = ref<string | null>(null)
  const step = ref(0)
  let stepTouched = false   // 用户是否主动选过步骤（用于区分"跟随状态"与"用户选择"）
  const tab = ref<'shots' | 'roles' | 'cost' | 'calls'>('shots')
  const scriptVer = ref(1)
  const selectedRoles = ref<Set<string>>(new Set(['child', 'teen', 'adult', 'mid', 'old']))
  const locked = ref(false)
  const ratio = ref<'v' | 'h'>('v')
  const player = ref({ pos: 0, playing: false })
  const exp = ref({ state: 'idle' as 'idle' | 'running' | 'done', pct: 0 })
  const projects = ref<any[]>([])
  // 真实内容（来自引擎，非演示数据）
  const detail = ref<any>(null)
  const script = ref<any>(null)
  const shots = ref<any>(null)
  const characters = ref<any[]>([])
  /** 最近一次生成的全过程文本（生成完成后保留，供用户回看） */
  const lastStream = ref('')
  /** 生成中的阶段提示（来自 SSE stage 事件） */
  const streamStage = ref('')
  /** 限流退避状态（来自 SSE wait 事件） */
  const streamWait = ref<{ reason: string; wait_s: number; attempt: number; max_attempts: number } | null>(null)
  /** 这一稿模型没写完（只写出了部分集） */
  const partial = ref(false)
  const contentBusy = ref(false)
  const contentError = ref('')
  const streamText = ref('')  // 生成过程实时文本（流式 token 累积）
  const status = ref('DRAFT') // 引擎业务状态（DRAFT→…→DELIVER），是流程进度的唯一事实来源
  const assets = ref<any[]>([]) // 引擎里已产出的真实素材（画面/成片）
  /** 引擎状态 → 允许到达的最远步骤。前进必须按顺序，越界会被拦下。 */
  const STEP_MAX_BY_STATUS: Record<string, number> = {
    DRAFT: 0, CP1_PENDING: 1, CHARACT: 2, CP2_PENDING: 3,
    PLANNED: 4, RUNNING: 5, CP3_PENDING: 6, DELIVER: 7,
  }
  const maxStep = computed(() => {
    const byStatus = STEP_MAX_BY_STATUS[status.value] ?? 0
    // 剧本已经写好、但引擎状态还没同步回前端时，第 2 步必须可达 ——
    // 否则用户点「确认这一稿，看大纲」会被自己的门禁挡住（实测踩过）。
    const byScript = script.value?.episodes?.length ? 1 : 0
    return Math.max(byStatus, byScript)
  })
  /** 素材可显示地址：引擎可能给绝对地址，也可能给 /api/... 相对地址。
   *  相对地址必须补上引擎基址，否则 <img src="/api/..."> 会指向前端源站 → 一片裂图。 */
  function assetUrl(u?: string | null): string {
    if (!u) return ''
    if (/^(https?:|data:|blob:)/i.test(u)) return u
    return `${engine.base}${u.startsWith('/') ? '' : '/'}${u}`
  }
  /** 流式生成剧本：读取 SSE 逐块更新 streamText，完成后落库结果写入 script。
   *  episodeIndex：只写第几集（逐集推进，省 token）；不传则按项目目标集数整批写。 */
  async function genScriptStream(version = 1, episodeIndex?: number | null): Promise<{ ok: boolean; error?: string }> {
    if (!currentId.value) return { ok: false, error: '没有当前项目' }
    contentBusy.value = true
    contentError.value = ''
    streamText.value = ''
    lastStream.value = ''
    streamWait.value = null
    partial.value = false
    const calls = useCallsStore()
    calls.clearLive()
    try {
      const res = await fetch(`${engine.base}/api/projects/${currentId.value}/script/generate/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Local-Token': engine.token },
        body: JSON.stringify(episodeIndex ? { version, episode_index: episodeIndex } : { version }),
      })
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
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
          const ev = block.split('\n').find(l => l.startsWith('event:'))?.slice(6).trim()
          const raw = block.split('\n').find(l => l.startsWith('data:'))?.slice(5).trim()
          if (!ev || !raw) continue
          try {
            const data = JSON.parse(raw)
            if (ev === 'stage') { streamStage.value = data.text || data.stage || '' }
            else if (ev === 'wait') {
              // 厂商限流退避：界面必须显示"在等什么、等多久"，否则像卡死
              streamWait.value = {
                reason: data.reason || '厂商限流',
                wait_s: Math.round(data.wait_s || 0),
                attempt: data.attempt || 1,
                max_attempts: data.max_attempts || 1,
              }
            }
            else if (ev === 'token') {
              streamText.value += data.t || ''
              // 模型开口了：说明重试已经成功，撤掉限流提示
              if (streamWait.value) streamWait.value = null
            }
            else if (ev === 'call') calls.pushLive(data)   // 实时模型调用日志
            else if (ev === 'meta') {
              // 本次生成的结果汇总，作为日志的最后一条
              const partialNote = data.partial ? `（模型没写完，只写出了 ${data.episodes || 0} 集）` : ''
              calls.pushLive({
                ts: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
                ability: 'text', model: '', endpoint: '', method: 'RESULT', path: '',
                status: 200, ms: 0, attempt: 1, error: '',
                note: `生成完成 · ${data.episodes || 0} 集 · ${data.chars || 0} 字${partialNote}`,
              })
              // 残缺：引擎已保住写完的那几集，但这一稿没写全，要如实告诉用户
              partial.value = !!data.partial
              // 引擎在剧本落库后已把状态推进到「等你确认剧本」，
              // 前端必须同步，否则下一步的按钮会被自己的门禁挡住。
              if (data.project_status) status.value = data.project_status
            }
            else if (ev === 'done') {
              script.value = data
              // 不清空流式文本：归档成"刚才的生成过程"，
              // 生成完成后用户还能回看模型是怎么写出来的（原来一闪而过）。
              lastStream.value = streamText.value
              streamText.value = ''
              streamStage.value = ''
              streamWait.value = null
              // 不在这里调 loadDetail：它会按引擎状态把界面跳到下一步，
              // 用户刚看完生成结果就被挪走会很难受。状态已在 meta 里同步过。
              return { ok: true }
            } else if (ev === 'error') {
              contentError.value = `${data.message || '生成失败'}${data.hint ? ' · ' + data.hint : ''}`
              streamWait.value = null
            }
          } catch { /* 忽略无法解析的块 */ }
        }
      }
      if (contentError.value) return { ok: false, error: contentError.value }
      if (!script.value) { contentError.value = '生成结束但没有返回剧本'; return { ok: false, error: contentError.value } }
      lastStream.value = streamText.value
      return { ok: true }
    } catch (e) {
      contentError.value = `生成失败：${(e as Error).message || '本地引擎未响应'}`
      return { ok: false, error: contentError.value }
    } finally {
      contentBusy.value = false
    }
  }
  let playTimer: ReturnType<typeof setInterval> | undefined
  let expTimer: ReturnType<typeof setInterval> | undefined
  function goto(i: number): boolean {
    const t = Math.max(0, Math.min(7, Number(i)))
    // 步骤门禁：不能跳过前面的确认直接跳到后面
    if (t > maxStep.value) {
      useUiStore().toast('先完成当前这一步，再往后走')
      return false
    }
    step.value = t
    stepTouched = true
    return true
  }
  /** 业务节点确认：交给引擎状态机推进，并把最新状态与素材同步回来。 */
  async function confirmStep(stepNo: number, payload: Record<string, any> = {}): Promise<boolean> {
    if (!currentId.value) { useUiStore().toast('还没有当前项目'); return false }
    const r = await engine.api<{ project_status: string }>(
      `/api/projects/${currentId.value}/steps/${stepNo}/advance`,
      { method: 'POST', body: { action: 'approve', payload } },
    )
    if (r?.project_status) {
      status.value = r.project_status
      await loadDetail()
      return true
    }
    useUiStore().toast(engine.error || '这一步暂时无法确认')
    return false
  }
  /** 从引擎加载项目真实内容（剧本/分镜可能为 null = 尚未生成）。 */
  async function loadDetail() {
    if (!currentId.value) return
    const r = await engine.api<any>(`/api/projects/${currentId.value}`)
    if (r) {
      detail.value = r
      script.value = r.script || null
      // 残缺标记跟着剧本一起存：刷新页面后仍要告诉用户"这一稿没写完"
      if (r.script?.partial) partial.value = true
      shots.value = r.shots || null
      characters.value = r.characters || []
      // 角色 id 是引擎生成的 chr_xxx，和前端预置的原型 id（child/teen/…）不是一回事。
      // 不对齐的话：第 3 步会显示"一个都没选"，确认角色时守卫 sel_ge_1 也会失败。
      const realIds = characters.value.map((c: any) => c.id)
      if (realIds.length && !realIds.some((id: string) => selectedRoles.value.has(id))) {
        selectedRoles.value = new Set(realIds)
      }
      status.value = r.status || 'DRAFT'
      assets.value = r.assets || []
      if (r.script_ver) scriptVer.value = r.script_ver
      // 步骤跟随引擎状态：打开项目就落在「当前该做的事」上，
      // 不会因为前端残留的 step 而停在已经完成或还没解锁的步骤。
      // 用户主动点过侧栏后（stepTouched），则尊重用户选择，不再强制拉回。
      if (!stepTouched || step.value > maxStep.value) step.value = maxStep.value
    }
  }
  /** 真实生成定妆图（调用已配置图片模型）。 */
  async function genCharacters(count = 5): Promise<{ ok: boolean; error?: string }> {
    if (!currentId.value) return { ok: false, error: '没有当前项目' }
    contentBusy.value = true
    contentError.value = ''
    try {
      const r = await engine.api<{ items: any[] }>(`/api/projects/${currentId.value}/characters/generate`, {
        method: 'POST', body: { count },
      })
      if (r?.items) { characters.value = r.items; return { ok: true } }
      contentError.value = engine.error || '定妆图生成失败，请检查图片模型配置'
      return { ok: false, error: contentError.value }
    } finally { contentBusy.value = false }
  }
  /** 真实生成剧本（调用已配置文本模型；未配置时返回明确错误）。 */
  async function genScript(version = 1): Promise<{ ok: boolean; error?: string }> {
    if (!currentId.value) return { ok: false, error: '没有当前项目' }
    contentBusy.value = true
    contentError.value = ''
    try {
      const r = await engine.api<any>(`/api/projects/${currentId.value}/script/generate`, {
        method: 'POST', body: { version },
      })
      if (r) { script.value = r; return { ok: true } }
      contentError.value = engine.error || '生成失败，请检查文本模型配置'
      return { ok: false, error: contentError.value }
    } finally { contentBusy.value = false }
  }
  /** 真实拆分镜头。 */
  async function genShots(shotCount = 12): Promise<{ ok: boolean; error?: string }> {
    if (!currentId.value) return { ok: false, error: '没有当前项目' }
    contentBusy.value = true
    contentError.value = ''
    try {
      const r = await engine.api<any>(`/api/projects/${currentId.value}/shots/generate`, {
        method: 'POST', body: { shot_count: shotCount },
      })
      if (r) { shots.value = r; return { ok: true } }
      contentError.value = engine.error || '拆分镜头失败，请检查文本模型配置'
      return { ok: false, error: contentError.value }
    } finally { contentBusy.value = false }
  }
  /** 最近一次创建的项目目标集数（引擎解析出来的，界面用它提示用户） */
  const createdEpisodeCount = ref(1)
  async function create(idea: string): Promise<boolean> {
    const r = await engine.api<{ id: string; episode_count?: number }>('/api/projects', {
      method: 'POST', body: { idea, template_id: 'life_3ep' },
    })
    if (r?.id) {
      currentId.value = r.id
      step.value = 0
      createdEpisodeCount.value = r.episode_count || 1
      return true
    }
    // 请求可能"实际成功但响应没回来"（引擎在写库后被重启/被杀，连接断掉）。
    // 这时界面报失败、刷新后项目却出现了 —— 必须回查确认，不能让用户以为白干了。
    const list = await engine.api<{ items: any[] }>('/api/projects')
    const hit = list?.items?.find((p: any) => p.idea_text === idea)
    if (hit?.id) {
      currentId.value = hit.id
      step.value = 0
      createdEpisodeCount.value = hit.episode_count || 1
      return true
    }
    return false
  }
  async function loadProjects() {
    const r = await engine.api<{ items: any[] }>('/api/projects')
    if (r?.items) projects.value = r.items
  }
  /** 软删项目：从列表移除，误删可恢复。删的是当前项目时清空选中态。 */
  async function remove(id: string): Promise<boolean> {
    const r = await engine.api(`/api/projects/${id}`, { method: 'DELETE' })
    if (!r) return false
    if (currentId.value === id) currentId.value = null
    await loadProjects()
    return true
  }
  async function loadTrash() {
    const r = await engine.api<{ items: any[] }>('/api/projects/trash/list')
    return r?.items || []
  }
  async function restore(id: string): Promise<boolean> {
    const r = await engine.api(`/api/projects/${id}/restore`, { method: 'POST' })
    if (!r) return false
    await loadProjects()
    return true
  }
  function toggleRole(k: string) {
    const s = new Set(selectedRoles.value)
    s.has(k) ? s.delete(k) : s.add(k)
    selectedRoles.value = s
  }
  function togglePlay() {
    if (player.value.playing) {
      player.value.playing = false
      clearInterval(playTimer)
      return
    }
    player.value.playing = true
    clearInterval(playTimer)
    playTimer = setInterval(() => {
      player.value.pos += 0.5
      if (player.value.pos >= 30) { player.value.pos = 30; player.value.playing = false; clearInterval(playTimer) }
    }, 120)
  }
  function startExport() {
    exp.value = { state: 'running', pct: 0 }
    clearInterval(expTimer)
    expTimer = setInterval(() => {
      exp.value.pct += 8
      if (exp.value.pct >= 100) {
        exp.value = { state: 'done', pct: 100 }
        clearInterval(expTimer)
      }
    }, 180)
  }
  /** 导出产物信息（真实结果，不是进度假动画）。 */
  const expResult = ref<{
    work_id?: string; format?: string; size_bytes?: number; frames?: number
    needs_ffmpeg?: boolean; reason?: string; download_url?: string; ratio?: string
  } | null>(null)
  async function exportWork(): Promise<any | null> {
    if (!currentId.value) return null
    exp.value = { state: 'running', pct: 0 }
    try {
      const r = await engine.api(`/api/projects/${currentId.value}/export`, {
        method: 'POST',
        body: { ratio: ratio.value === 'v' ? '9:16' : '16:9', with_subtitle: true, ai_badge: true },
      })
      expResult.value = r || null
      exp.value = { state: 'done', pct: 100 }
      return r
    } catch (e) {
      exp.value = { state: 'idle', pct: 0 }
      expResult.value = null
      throw e
    }
  }
  return {
    currentId, step, tab, scriptVer, selectedRoles, locked, ratio, player, exp, expResult, projects,
    detail, script, shots, characters, contentBusy, contentError, streamText, lastStream, streamStage, streamWait, partial,
    status, assets, maxStep, assetUrl, createdEpisodeCount,
    goto, confirmStep, create, loadProjects, loadDetail, remove, loadTrash, restore,
    genScript, genScriptStream, genShots, genCharacters, toggleRole,
    togglePlay, startExport, exportWork,
  }
})
