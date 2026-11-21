import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { engine } from '@/api/engine'
import { useUiStore } from './ui'
/** 项目与制作流程：状态、步骤、角色选择、生成/播放/导出。
 *  守卫在引擎，前端的 step 只用于界面呈现；所有内容来自引擎真实数据。 */
export const useProjectStore = defineStore('project', () => {
  const currentId = ref<string | null>(null)
  const step = ref(0)
  let stepTouched = false   // 用户是否主动选过步骤（用于区分"跟随状态"与"用户选择"）
  const tab = ref<'shots' | 'roles' | 'cost'>('shots')
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
  const maxStep = computed(() => STEP_MAX_BY_STATUS[status.value] ?? 0)
  /** 流式生成剧本：读取 SSE 逐块更新 streamText，完成后落库结果写入 script。 */
  async function genScriptStream(version = 1): Promise<{ ok: boolean; error?: string }> {
    if (!currentId.value) return { ok: false, error: '没有当前项目' }
    contentBusy.value = true
    contentError.value = ''
    streamText.value = ''
    try {
      const res = await fetch(`${engine.base}/api/projects/${currentId.value}/script/generate/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Local-Token': engine.token },
        body: JSON.stringify({ version }),
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
            if (ev === 'stage') { /* 阶段提示由 gen-busy 展示 */ }
            else if (ev === 'token') streamText.value += data.t || ''
            else if (ev === 'done') { script.value = data; streamText.value = ''; return { ok: true } }
            else if (ev === 'error') {
              contentError.value = `${data.message || '生成失败'}${data.hint ? ' · ' + data.hint : ''}`
            }
          } catch { /* 忽略无法解析的块 */ }
        }
      }
      if (contentError.value) return { ok: false, error: contentError.value }
      if (!script.value) { contentError.value = '生成结束但没有返回剧本'; return { ok: false, error: contentError.value } }
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
      shots.value = r.shots || null
      characters.value = r.characters || []
      status.value = r.status || 'DRAFT'
      assets.value = r.assets || []
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
  async function create(idea: string): Promise<boolean> {
    const r = await engine.api<{ id: string }>('/api/projects', {
      method: 'POST', body: { idea, template_id: 'life_3ep' },
    })
    if (r?.id) {
      currentId.value = r.id
      step.value = 0
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
  async function exportWork(): Promise<any | null> {
    if (!currentId.value) return null
    return engine.api(`/api/projects/${currentId.value}/export`, {
      method: 'POST',
      body: { ratio: ratio.value === 'v' ? '9:16' : '16:9', with_subtitle: true, ai_badge: true },
    })
  }
  return {
    currentId, step, tab, scriptVer, selectedRoles, locked, ratio, player, exp, projects,
    detail, script, shots, characters, contentBusy, contentError, streamText,
    status, assets, maxStep,
    goto, confirmStep, create, loadProjects, loadDetail, remove, loadTrash, restore,
    genScript, genScriptStream, genShots, genCharacters, toggleRole,
    togglePlay, startExport, exportWork,
  }
})
