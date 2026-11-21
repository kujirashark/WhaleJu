import { defineStore } from 'pinia'
import { ref } from 'vue'
import { engine } from '@/api/engine'
/** 模型调用日志：让每次真实调用可见，而不是黑盒。
 *  live —— 当前流式生成会话的实时记录（SSE 逐条推送）
 *  items —— 引擎侧最近的历史记录（覆盖图片/视频/镜头等所有能力） */
export interface CallEntry {
  ts: string
  ability: string
  model: string
  endpoint: string
  method: string
  path: string
  status: number
  ms: number
  attempt: number
  error: string
  note: string
}
export const useCallsStore = defineStore('calls', () => {
  const live = ref<CallEntry[]>([])
  const items = ref<CallEntry[]>([])
  function pushLive(e: CallEntry) {
    live.value.push(e)
    if (live.value.length > 100) live.value.shift()
  }
  function clearLive() { live.value = [] }
  async function load(limit = 60) {
    const r = await engine.api<{ items: CallEntry[] }>(`/api/calls?limit=${limit}`)
    items.value = r?.items || []
    return items.value
  }
  return { live, items, pushLive, clearLive, load }
})
