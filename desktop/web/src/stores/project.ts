import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'
/** 项目与制作流程：状态、步骤、角色选择、生成/播放/导出。
 *  守卫在引擎，前端的 step 只用于界面呈现；所有内容来自引擎真实数据。 */
export const useProjectStore = defineStore('project', () => {
  const currentId = ref<string | null>(null)
  const step = ref(3)
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
  let playTimer: ReturnType<typeof setInterval> | undefined
  let expTimer: ReturnType<typeof setInterval> | undefined
  function goto(i: number) { step.value = Math.max(0, Math.min(7, Number(i))) }
  /** 从引擎加载项目真实内容（剧本/分镜可能为 null = 尚未生成）。 */
  async function loadDetail() {
    if (!currentId.value) return
    const r = await engine.api<any>(`/api/projects/${currentId.value}`)
    if (r) {
      detail.value = r
      script.value = r.script || null
      shots.value = r.shots || null
      characters.value = r.characters || []
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
    detail, script, shots, characters, contentBusy, contentError,
    goto, create, loadProjects, loadDetail, genScript, genShots, genCharacters, toggleRole,
    togglePlay, startExport, exportWork,
  }
})
