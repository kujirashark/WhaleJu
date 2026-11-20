import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'
/**
 * 模型设置槽位（去演示化）：
 * - 默认全部「未设置」，没有任何来源被假定可用。
 * - 每个来源（平台代采 / 自带密钥 / 本地模型）都必须填服务地址 + 模型标识。
 * - 保存后状态为「待测试」，必须真实连接测试通过才可用于生成。
 * 密钥与配置只在内存暂存，提交后草稿清空，任何接口不回显明文。
 */
export interface SlotDraft {
  source: 'owned' | 'local' | 'proxy'
  providerKind: string
  endpoint: string
  model: string
  credential: string
}
export const useSettingsStore = defineStore('settings', () => {
  // 槽位来源选择：默认空字符串 = 未设置
  const slots = ref<Record<string, string>>({ text: '', image: '', video: '', speech: '' })
  // 每个槽位的真实配置草稿
  const drafts = ref<Record<string, SlotDraft>>({
    text: { source: 'owned', providerKind: 'openai_compat', endpoint: '', model: '', credential: '' },
    image: { source: 'owned', providerKind: 'openai_compat', endpoint: '', model: '', credential: '' },
    video: { source: 'owned', providerKind: 'openai_compat', endpoint: '', model: '', credential: '' },
    speech: { source: 'owned', providerKind: 'openai_compat', endpoint: '', model: '', credential: '' },
  })
  // 引擎返回的权威状态
  const serverSlots = ref<Record<string, any>>({})
  const probeResults = ref<Record<string, string>>({})
  const probing = ref<Record<string, boolean>>({})
  const SOURCE_KIND: Record<string, SlotDraft['source']> = { key: 'owned', local: 'local', plat: 'proxy' }
  /** 界面选项(key/local/plat) → 引擎来源(owned/local/proxy)，必须同步进草稿，
   * 否则选了「本地」仍按 owned 提交，会误报需要密钥。 */
  function pick(slot: string, value: string) {
    slots.value[slot] = value
    const mapped = SOURCE_KIND[value]
    if (mapped) drafts.value[slot].source = mapped
  }
  /** 从引擎加载已保存配置（服务端是唯一事实源）。 */
  async function load() {
    const r = await engine.api<{ slots: Record<string, any> }>('/api/model-configs')
    if (r?.slots) {
      serverSlots.value = r.slots
      for (const [slot, info] of Object.entries(r.slots)) {
        const s = (info as any).source
        // 只在服务端确实有配置时回写；不覆盖用户此刻正在点选的来源
        if (s === 'owned') slots.value[slot] = 'key'
        else if (s === 'local') slots.value[slot] = 'local'
        else if (s === 'proxy') slots.value[slot] = 'plat'
        // 回写草稿来源：刷新页面后再次保存不能把已有 local/proxy 配置覆盖成默认 owned
        if (s === 'owned' || s === 'local' || s === 'proxy') drafts.value[slot].source = s
      }
    }
  }
  /** 保存当前槽位：endpoint + model 必填；密钥按来源要求。 */
  async function saveOne(slot: string): Promise<boolean> {
    const choice = slots.value[slot]
    if (!choice) return false
    const d = drafts.value[slot]
    const endpoint = (d.endpoint || serverSlots.value[slot]?.endpoint || '').trim()
    const model = (d.model || serverSlots.value[slot]?.model || '').trim()
    if (!endpoint || !model) {
      probeResults.value[slot] = '请先填写服务地址和模型标识'
      return false
    }
    const r = await engine.api(`/api/model-configs/${slot}`, {
      method: 'PUT',
      body: {
        source: d.source,
        provider_kind: d.providerKind,
        name: `${slot} · ${choice}`,
        endpoint,
        model,
        credential: d.credential || null,
      },
    })
    if (r) {
      d.credential = '' // 提交后内存即清，界面不再回显
      probeResults.value[slot] = '已保存，请点「测试连接」验证'
    }
    return !!r
  }
  /** 保存所有已选槽位。 */
  async function save(): Promise<number> {
    let saved = 0
    for (const slot of Object.keys(slots.value)) {
      if (slots.value[slot] && await saveOne(slot)) saved++
    }
    await load()
    return saved
  }
  /** 真实连接测试：通过才 verified=1，否则明确失败。 */
  async function test(slot: string): Promise<boolean> {
    probing.value[slot] = true
    probeResults.value[slot] = ''
    try {
      // 若用户改了草稿但未保存，先保存再测试
      const d = drafts.value[slot]
      if (d.endpoint || d.model || d.credential) await saveOne(slot)
      const r = await engine.api<{ ok: boolean; verified: boolean; error?: string; price_hint?: string }>(
        `/api/model-configs/${slot}/test`, { method: 'POST' },
      )
      probeResults.value[slot] = r?.ok
        ? `连接测试通过${r.price_hint ? ' · ' + r.price_hint : ''}`
        : `连接测试失败：${r?.error || '请检查地址和密钥'}`
      await load()
      return !!r?.ok
    } finally {
      probing.value[slot] = false
    }
  }
  return {
    slots, drafts, serverSlots, probeResults, probing,
    pick, load, save, saveOne, test,
  }
})
