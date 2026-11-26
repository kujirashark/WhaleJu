import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'

/**
 * 模型设置槽位（去演示化）：
 * - 默认全部「未设置」，没有任何来源被假定可用。
 * - 每个来源（自带密钥 / 本地模型）都必须填服务地址 + 模型标识。纯开源版无平台代采。
 * - 保存后状态为「待测试」，必须真实连接测试通过才可用于生成。
 * 密钥与配置只在内存暂存，提交后草稿清空，任何接口不回显明文。
 */
export interface SlotDraft {
  source: 'owned' | 'local'
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

  const SOURCE_KIND: Record<string, SlotDraft['source']> = { key: 'owned', local: 'local' }

  /** 界面选项(key/local) → 引擎来源(owned/local)，必须同步进草稿，
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
        const i = info as any
        const s = i.source
        // 只在服务端确实有配置时回写；不覆盖用户此刻正在点选的来源
        if (s === 'owned') slots.value[slot] = 'key'
        else if (s === 'local') slots.value[slot] = 'local'
        // 回写草稿来源：刷新页面后再次保存不能把已有配置覆盖成默认 owned
        if (s === 'owned' || s === 'local') {
          drafts.value[slot].source = s
          // 完整回填已保存配置：否则重开设置页输入框是空的，看起来像没保存
          if (i.endpoint) drafts.value[slot].endpoint = i.endpoint
          if (i.model) drafts.value[slot].model = i.model
          // 密钥不回显明文；用占位掩码提示"已保存"，用户留空即沿用
          drafts.value[slot].credential = ''
        }
        // 自愈：服务端已验证但界面还残留"请点测试连接"的旧提示时纠正，
        // 否则「已验证可用」和红色提示会同时出现，误导用户
        if (i.verified && (probeResults.value[slot] || '').includes('请点「测试连接」')) {
          probeResults.value[slot] = '这个能力已验证可用，可以开始生成'
        }
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
    // 已验证且配置完全没变、也没输入新密钥时，无需再写库——直接保留现状。
    // 这样旧引擎进程也不会因「密钥留空」误报 400，用户重开设置页点保存不会有假失败。
    const server = serverSlots.value[slot]
    if (server?.verified && !d.credential && server.endpoint === endpoint && server.model === model) {
      probeResults.value[slot] = '配置未改动，这个能力仍处于已验证可用状态'
      return true
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
      // 已测通的配置再次保存时，别再让用户去点测试连接——服务端保留了 verified
      const verified = !!r?.slot?.verified
      probeResults.value[slot] = verified
        ? '已保存，这个能力仍处于已验证可用状态'
        : '已保存，请点「测试连接」验证'
    } else {
      // 保存失败必须覆盖旧提示，否则界面上会同时出现「已验证」和旧的红色提示，自相矛盾
      probeResults.value[slot] = `保存失败：${engine.error || '本地引擎未响应'}`
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
    engine.error = ''
    try {
      // 若用户改了草稿但未保存，先保存再测试；保存失败必须中止，
      // 否则会用库里的旧配置去探测，报出与界面无关的错误
      const d = drafts.value[slot]
      if (d.endpoint || d.model || d.credential) {
        const saved = await saveOne(slot)
        if (!saved) {
          probeResults.value[slot] = probeResults.value[slot] || `保存失败：${engine.error || '请检查地址和模型'}`
          return false
        }
      }
      const r = await engine.api<{ ok: boolean; verified: boolean; error?: string; price_hint?: string; warning?: string }>(
        `/api/model-configs/${slot}/test`, { method: 'POST' },
      )
      if (r?.ok) {
        // 连接成功但模型标识可能填错（如把图片模型填进视频槽）：
        // 这类问题测试连接查不出来，必须明确提示，否则生成时才炸。
        probeResults.value[slot] = r.warning
          ? `连接测试通过 · ${r.price_hint || ''}｜${r.warning}`
          : `连接测试通过${r.price_hint ? ' · ' + r.price_hint : ''}`
      } else {
        probeResults.value[slot] = `连接测试失败：${r?.error || (engine.error ? `引擎错误：${engine.error}` : '请检查地址和密钥')}`
      }
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
