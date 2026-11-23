import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'
export interface GenStartResult {
  ok: boolean
  error?: string
  hint?: string
  code?: string          // 引擎错误码：E2001=额度不足 / E4001=没配模型
  need?: number          // 需要的额度
  balance?: number       // 当前余额
}
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
  asset_id?: string | null
  /** 引擎给的本机素材地址（图片或视频，永久有效） */
  media_url?: string | null
  /** 素材形态：image=静态画面 / video=视频片段 */
  kind?: 'image' | 'video'
  ability?: string
  fail_reason?: string | null
}
/** 引擎里已落库的镜头素材（持久化）：引擎重启、刷新页面后画面都还在。 */
const persisted = ref<GenItem[]>([])
/** 进度来自数据库（引擎重启过，内存批次没了）——界面要如实告诉用户 */
const restoredFromDb = ref(false)
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
  /** 最近一次失败的错误码/提示/额度数字：界面据此给出正确出路，而不是笼统一句"配置模型" */
  const lastErrorCode = ref('')
  const lastErrorHint = ref('')
  const lastErrorNeed = ref<number | null>(null)
  const lastErrorBalance = ref<number | null>(null)
  /** 致命原因：厂商不支持这个能力（如把图片模型填进视频槽），已停批 */
  const fatalReason = ref('')
  /** 本批次的生成口径：ability(image/video)、单价、预估花费、计费方式 */
  const ability = ref<'image' | 'video'>('image')
  const unitPrice = ref(0)
  const estimatedCost = ref(0)
  const billing = ref<'own_key' | 'platform_credits' | ''>('')
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
    fatalReason.value = p.fatal_reason || ''
    // 进度里带着本批次的计费口径，刷新页面后也能显示正确的单价与预估
    if (p.ability) ability.value = p.ability
    if (typeof p.unit_price === 'number') unitPrice.value = p.unit_price
    if (typeof p.estimated_cost === 'number') estimatedCost.value = p.estimated_cost
  }
  function reset() {
    stopPolling()
    batchId.value = ''; done.value = 0; total.value = 0; running.value = 0
    failed.value = 0; queued.value = 0; paused.value = false; eta.value = null
    items.value = []; failedItems.value = []; lastError.value = ''; notStarted.value = true
    lastErrorCode.value = ''; lastErrorHint.value = ''
    lastErrorNeed.value = null; lastErrorBalance.value = null
    fatalReason.value = ''
    ability.value = 'image'; unitPrice.value = 0; estimatedCost.value = 0; billing.value = ''
    restoredFromDb.value = false
  }
  /**
   * 加载已落库的镜头素材。
   * 生成批次只存在引擎内存里，引擎一重启 progress 就变"未开始"，
   * 用户明明生成好 12 张画面却什么都看不到。这里从库里把画面还原出来。
   */
  async function loadPersisted(projectId: string) {
    const r = await engine.api<{ items: GenItem[] }>(`/api/projects/${projectId}/shots/media`)
    if (r?.items) persisted.value = r.items
  }
  /**
   * 画面清单：优先用引擎的持久化素材（刷新/重启后仍在），
   * 内存批次只用来补充"生成中"这类实时状态。
   */
  function visibleItems(): GenItem[] {
    const live = items.value
    if (!live.length) return persisted.value
    // 内存里有批次：把库里的素材地址合并进去（批次里的 asset_id 可能还没回写）
    const byShot = new Map(persisted.value.map((p) => [p.shot_id, p]))
    return live.map((it) => {
      const p = byShot.get(it.shot_id)
      if (!p) return it
      // 库里的状态更权威：描述改过（edited）要盖过内存批次的 done
      const status = p.status === 'edited' ? 'edited' : (it.media_url ? it.status : p.status)
      if (it.media_url && status === it.status) return it
      return {
        ...it,
        status,
        media_url: it.media_url || p.media_url,
        asset_id: it.asset_id || p.asset_id,
        kind: p.kind || (it.ability === 'video' ? 'video' : 'image'),
        scene_desc: p.scene_desc || it.scene_desc,
      }
    })
  }
  /**
   * 开始真实生成批次。返回 { ok, error }。
   * 引擎未连接、未配置模型、额度不足等都以明确错误返回，不做本地演示。
   */
  async function start(projectId: string, shotCount = 12): Promise<GenStartResult> {
    stopPolling()
    lastError.value = ''
    if (!engine.online) {
      lastError.value = '本地引擎未连接，无法生成'
      return { ok: false, error: lastError.value }
    }
    engine.lastError = {}
    const r = await engine.api<{ batch_id: string; route_reason: string; ability?: string;
                                unit_price?: number; estimated_cost?: number; billing?: string }>(
      `/api/projects/${projectId}/generation/start`,
      { method: 'POST', body: { shot_count: shotCount } },
    )
    if (r?.batch_id) {
      routeReason.value = r.route_reason || ''
      ability.value = (r.ability as 'image' | 'video') || 'image'
      unitPrice.value = r.unit_price || 0
      estimatedCost.value = r.estimated_cost || 0
      billing.value = (r.billing as any) || ''
      apply({ batch_id: r.batch_id, done: 0, total: shotCount, queued: shotCount })
      await poll(projectId)
      pollTimer = setInterval(() => poll(projectId), 500)
      return { ok: true }
    }
    // 引擎拒绝：显示真实原因（额度不足 / 没配模型 / 厂商限流……），
    // 绝不用「去配置模型」这种通用话术盖掉真实原因——那会让用户一直找错方向。
    const d = engine.lastError
    lastError.value = engine.error || '生成被拒绝，请检查模型配置与额度'
    lastErrorCode.value = d?.code || ''
    lastErrorHint.value = d?.hint || ''
    lastErrorNeed.value = d?.need ?? null
    lastErrorBalance.value = d?.balance ?? null
    if (d?.code === 'E2001') {
      return {
        ok: false, error: lastError.value,
        code: d.code, need: d.need, balance: d.balance,
        hint: d.hint || '可以充值额度，或改成用你自己的 API 密钥（不消耗平台额度）',
      }
    }
    return { ok: false, error: lastError.value, code: d?.code, hint: d?.hint }
  }
  async function poll(projectId: string) {
    const p = await engine.api(`/api/projects/${projectId}/generation/progress`)
    if (p) apply(p)
    if (p?.restored_from_db) restoredFromDb.value = true
    if (p && total.value > 0 && done.value >= total.value && !paused.value) stopPolling()
  }
  /**
   * 只重新生成某一个镜头（其它镜头不动）。
   * 用户要的是"这张不满意，换一张"，整批重跑等于白烧一轮额度。
   */
  async function regenerateShot(projectId: string, shotId: string, ability?: 'image' | 'video') {
    const r = await engine.api<{ ok: boolean; shot_id: string; media_url?: string; fail_reason?: string }>(
      `/api/projects/${projectId}/shots/${shotId}/regenerate`,
      { method: 'POST', body: { ability: ability || null } },
    )
    if (!r) {
      lastError.value = engine.error || '重新生成失败'
      return { ok: false, error: lastError.value }
    }
    // 把新素材写回列表对应位置，界面立刻显示新画面
    const idx = items.value.findIndex((i) => i.shot_id === shotId)
    if (idx >= 0 && r.media_url) {
      items.value[idx] = {
        ...items.value[idx],
        status: 'done',
        asset_id: (r as any).asset_id ?? items.value[idx].asset_id,
        media_url: r.media_url,
        fail_reason: null,
      }
      apply({ items: items.value, done: done.value, total: total.value, failed: failed.value })
    }
    // 持久化列表也要更新：引擎重启后靠它显示画面
    const pidx = persisted.value.findIndex((i) => i.shot_id === shotId)
    if (pidx >= 0 && r.media_url) {
      persisted.value[pidx] = {
        ...persisted.value[pidx],
        status: 'done',
        asset_id: (r as any).asset_id ?? persisted.value[pidx].asset_id,
        media_url: r.media_url,
        fail_reason: null,
      }
    }
    return { ok: true, media_url: r.media_url }
  }
  /** 刷新页面后恢复进行中的批次：进度在引擎里，这里重新拉一次并继续盯。 */
  async function restore(projectId: string) {
    stopPolling()
    // 先把库里已生成的画面拉回来：引擎重启过也能看见真实产物
    await loadPersisted(projectId)
    await poll(projectId)
    if (total.value > 0 && done.value < total.value) {
      pollTimer = setInterval(() => poll(projectId), 800)
    }
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
    routeReason, lastError, lastErrorCode, lastErrorHint, lastErrorNeed, lastErrorBalance,
    fatalReason, ability, unitPrice, estimatedCost, billing, notStarted,
    persisted, restoredFromDb, visibleItems,
    start, poll, restore, pause, resume, stopPolling, reset, regenerateShot, loadPersisted,
  }
})
