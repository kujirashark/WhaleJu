import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'
/** 项目与制作流程：状态、步骤、角色选择、生成/播放/导出。
 *  守卫在引擎，前端的 step 只用于演示动画与界面呈现。 */
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
  let playTimer: ReturnType<typeof setInterval> | undefined
  let expTimer: ReturnType<typeof setInterval> | undefined
  function goto(i: number) { step.value = Math.max(0, Math.min(7, Number(i))) }
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
    goto, create, loadProjects, toggleRole,
    togglePlay, startExport, exportWork,
  }
})
