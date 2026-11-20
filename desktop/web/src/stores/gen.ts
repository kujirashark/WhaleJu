import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'
/** 生成进度（设计 §6.7 useGenStore）：只渲染引擎事实，不做业务判断。
 *  引擎离线时降级为本地演示动画（明确标注 demo）。 */
export interface GenItem {
  shot_id: string
  scene_desc: string
  status: string
  cost: number
}
export const useGenStore = defineStore('gen', () => {
  const batchId = ref('')
  const done = ref(0)
  const total = ref(12)
  const running = ref(0)
  const failed = ref(0)
  const queued = ref(12)
  const paused = ref(false)
  const eta = ref<number | null>(null)
  const items = ref<GenItem[]>([])
  const failedItems = ref<any[]>([])
  const isDemo = ref(false)
  const routeReason = ref('')
  let pollTimer: ReturnType<typeof setInterval> | undefined
  let demoTimer: ReturnType<typeof setInterval> | undefined
  function apply(p: any) {
    if (!p) return
    batchId.value = p.batch_id || ''
    done.value = p.done ?? 0
    total.value = p.total ?? 12
    running.value = p.running ?? 0
    failed.value = p.failed ?? 0
    queued.value = p.queued ?? 0
    paused.value = !!p.paused
    eta.value = p.eta_s ?? null
    items.value = p.items || []
    failedItems.value = p.failed_items || []
  }
  async function start(projectId: string, shotCount = 12): Promise<boolean> {
    stopPolling()
    const r = await engine.api<{ batch_id: string; route_reason: string }>(
      `/api/projects/${projectId}/generation/start`,
      { method: 'POST', body: { shot_count: shotCount } },
    )
    if (r?.batch_id) {
      isDemo.value = false
      routeReason.value = r.route_reason || ''
      await poll(projectId)
      pollTimer = setInterval(() => poll(projectId), 400)
      return true
    }
    startDemo()
    return false
  }
  async function poll(projectId: string) {
    const p = await engine.api(`/api/projects/${projectId}/generation/progress`)
    if (p) apply(p)
    if (p && done.value >= total.value && !paused.value) stopPolling()
  }
  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = undefined }
    if (demoTimer) { clearInterval(demoTimer); demoTimer = undefined }
  }
  function startDemo() {
    isDemo.value = true
    done.value = 0
    total.value = 12
    paused.value = false
    clearInterval(demoTimer)
    demoTimer = setInterval(() => {
      if (paused.value) return
      if (done.value >= total.value) { clearInterval(demoTimer); return }
      done.value++
    }, 900)
  }
  async function pause(projectId: string) {
    if (isDemo.value) { paused.value = !paused.value; return }
    const r = await engine.api(`/api/projects/${projectId}/generation/pause`, { method: 'POST' })
    if (r) apply(r)
  }
  async function resume(projectId: string) {
    if (isDemo.value) { paused.value = false; return }
    const r = await engine.api(`/api/projects/${projectId}/generation/resume`, { method: 'POST' })
    if (r) apply(r)
    if (!pollTimer) pollTimer = setInterval(() => poll(projectId), 400)
  }
  function finishDemo() {
    clearInterval(demoTimer)
    done.value = total.value
    paused.value = false
  }
  return {
    batchId, done, total, running, failed, queued, paused, eta, items, failedItems, isDemo, routeReason,
    start, poll, pause, resume, stopPolling, startDemo, finishDemo,
  }
})
