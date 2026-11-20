import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'
/** 模型设置槽位。Key 输入框内容只在内存，提交后立即清空，不回显。 */
export const useSettingsStore = defineStore('settings', () => {
  const slots = ref<Record<string, string>>({ text: 'local', image: 'key', video: 'key', voice: 'local' })
  const keyDrafts = ref<Record<string, string>>({})
  const probeResults = ref<Record<string, string>>({})
  function pick(slot: string, value: string) { slots.value[slot] = value }
  async function test(slot: string) {
    const r = await engine.api<{ ok: boolean; price_hint?: string }>(`/api/model-configs/${slot}/test`, { method: 'POST' })
    probeResults.value[slot] = r
      ? (r.ok ? `连接测试通过${r.price_hint ? ' · ' + r.price_hint : ''}` : '连接测试失败，请检查密钥')
      : '演示模式：未连接引擎'
  }
  async function save() {
    let saved = 0
    for (const [slot, value] of Object.entries(slots.value)) {
      const r = await engine.api(`/api/model-configs/${slot}`, {
        method: 'PUT',
        body: {
          source: value === 'key' ? 'owned' : value === 'local' ? 'local' : 'proxy',
          provider_kind: value === 'local' ? 'ollama' : 'openai_compat',
          name: `${slot} · ${value}`,
          endpoint: null,
          credential: keyDrafts.value[slot] || null,
        },
      })
      if (r) saved++
      keyDrafts.value[slot] = '' // 提交后内存即清，界面不再回显
    }
    return saved
  }
  return { slots, keyDrafts, probeResults, pick, test, save }
})
