import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'
/** 钱包：余额永远以引擎返回为准；前端只展示，不自行累加。 */
export const useWalletStore = defineStore('wallet', () => {
  const balance = ref(86.4)
  const plan = ref('p1')
  const paying = ref(false)
  async function refresh() {
    const w = await engine.api<{ balance: number }>('/api/wallet')
    if (w && typeof w.balance === 'number') balance.value = w.balance
  }
  async function recharge(): Promise<number | null> {
    paying.value = true
    try {
      const r = await engine.api<{ balance: number; amount: number }>('/api/wallet/recharge', {
        method: 'POST', body: { plan_id: plan.value },
      })
      if (r && typeof r.balance === 'number') {
        balance.value = r.balance
        return r.amount
      }
      return null
    } finally {
      paying.value = false
    }
  }
  return { balance, plan, paying, refresh, recharge }
})
