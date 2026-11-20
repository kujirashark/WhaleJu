import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'
/**
 * 生成进度（设计 §6.7 useGenStore）：只渲染引擎事实，不做业务判断。
 * 去演示化：没有演示降级动画。引擎未就绪 / 未配置模型时给出明确错误，
 * 由调用方提示用户去设置，绝不伪造进度。
 */
export interface GenItem {
  shot_id: string
  scene_desc: string
  status: string
  cost: number
  asset_ref?: string | null
  fail_reason?: string | null
}
export const useGenStore = defineStore('gen', () => {
  const batchId = ref('')
  const done = ref(0)
  const total = ref(0)
  const running = ref(0)
  const failed = ref(0)
  const queued = ref(0)
  const paused = ref(false)
  const eta = ref<number | null>(null)
  const items = ref<GenItem[]>([])
  const failedItems = ref<any[]>([])
  const routeReason = ref('')
  const lastError = ref('')
  const notStarted = ref(true)
  let pollTimer: ReturnType<typeof setInterval> | undefined
  function apply(p: any) {
    if (!p) return
    batchId.value = p.batch_id || ''
    done.value = p.done ?? 0
    total.value = p.total ?? 0
    running.value = p.running ?? 0
    failed.value = p.failed ?? 0
    queued.value = p.queued ?? 0
    paused.value = !!p.paused
    eta.value = p.eta_s ?? null
    items.value = p.items || []
    failedItems.value = p.failed_items || []
    notStarted.value = !!p.not_started
  }
  function reset() {
    stopPolling()
    batchId.value = ''; done.value = 0; total.value = 0; running.value = 0
    failed.value = 0; queued.value = 0; paused.value = false; eta.value = null
    items.value = []; failedItems.value = []; lastError.value = ''; notStarted.value = true
  }
  /**
   * 开始真实生成批次。返回 { ok, error }。
   * 引擎未连接、未配置模型、额度不足等都以明确错误返回，不做本地演示。
   */
  async function start(projectId: string, shotCount = 12): Promise<{ ok: boolean; error?: string; hint?: string }> {
    stopPolling()
    lastError.value = ''
    if (!engine.online) {
      lastError.value = '本地引擎未连接，无法生成'
      return { ok: false, error: lastError.value }
    }
    const r = await engine.api<{ batch_id: string; route_reason: string }>(
      `/api/projects/${projectId}/generation/start`,
      { method: 'POST', body: { shot_count: shotCount } },
    )
    if (r?.batch_id) {
      routeReason.value = r.route_reason || ''
      apply({ batch_id: r.batch_id, done: 0, total: shotCount, queued: shotCount })
      await poll(projectId)
      pollTimer = setInterval(() => poll(projectId), 500)
      return { ok: true }
    }
    // 引擎拒绝：从 error 中提取可读提示（api() 已把错误文本写入 engine.error）
    lastError.value = engine.error || '生成被拒绝，请检查模型配置与额度'
    return { ok: false, error: lastError.value, hint: '到设置里配置模型并测试连接后再试' }
  }
  async function poll(projectId: string) {
    const p = await engine.api(`/api/projects/${projectId}/generation/progress`)
    if (p) apply(p)
    if (p && total.value > 0 && done.value >= total.value && !paused.value) stopPolling()
  }
  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = undefined }
  }
  async function pause(projectId: string) {
    const r = await engine.api(`/api/projects/${projectId}/generation/pause`, { method: 'POST' })
    if (r) apply(r)
  }
  async function resume(projectId: string) {
    const r = await engine.api(`/api/projects/${projectId}/generation/resume`, { method: 'POST' })
    if (r) apply(r)
    if (!pollTimer) pollTimer = setInterval(() => poll(projectId), 500)
  }
  return {
    batchId, done, total, running, failed, queued, paused, eta, items, failedItems,
    routeReason, lastError, notStarted,
    start, poll, pause, resume, stopPolling, reset,
  }
})
