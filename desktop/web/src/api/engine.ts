/**
 * 引擎连接层：Tauri 环境通过 IPC 拿到端口与令牌；浏览器预览走固定 7420。
 * 令牌只保存在内存，不写 localStorage，不出现在任何 URL。
 */
import { invoke } from '@tauri-apps/api/core'
export interface EngineInfo {
  running: boolean
  port: number
  token: string
  base_url: string
  error?: string | null
}
class EngineClient {
  base = ''
  token = ''
  online = false
  error = ''
  mode: 'booting' | 'tauri' | 'browser' = 'booting'
  /** 连接完成的 Promise，供 UI 等待（避免 ref 追踪不到普通属性变化） */
  ready!: Promise<boolean>
  private async isTauri(): Promise<boolean> {
    return typeof window !== 'undefined' && ('__TAURI_INTERNALS__' in window || '__TAURI__' in window)
  }
  async connect(): Promise<boolean> {
    let info: EngineInfo | null = null
    if (await this.isTauri()) {
      this.mode = 'tauri'
      try {
        info = await invoke<EngineInfo>('start_engine')
      } catch (e) {
        this.error = String(e)
      }
    } else {
      this.mode = 'browser'
      try {
        const h = await fetch('http://127.0.0.1:7420/health', { cache: 'no-store' })
        if (h.ok) {
          const t = await fetch('http://127.0.0.1:7420/api/local-token', { cache: 'no-store' })
          const j = await t.json()
          info = { running: true, port: 7420, token: j.token, base_url: 'http://127.0.0.1:7420' }
        }
      } catch (e) {
        this.error = '未检测到本地引擎，请先启动鲸鲨漫剧桌面应用'
      }
    }
    if (info?.running && info.base_url && info.token) {
      this.base = info.base_url
      this.token = info.token
      this.online = true
      return true
    }
    this.online = false
    return false
  }
  /** 初始化连接（幂等），返回同一个 Promise */
  init(): Promise<boolean> {
    if (!this.ready) this.ready = this.connect()
    return this.ready
  }
  async api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T | null> {
    if (!this.online) return null
    try {
      const res = await fetch(this.base + path, {
        method: opts.method || 'GET',
        headers: { 'Content-Type': 'application/json', 'X-Local-Token': this.token },
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      })
      if (!res.ok) throw new Error(`${res.status} ${(await res.text()).slice(0, 140)}`)
      return (await res.json()) as T
    } catch (e) {
      this.error = String((e as Error).message || e)
      console.warn('[engine] API 失败:', path, this.error)
      return null
    }
  }
  async openFolder(kind: 'data' | 'works'): Promise<string | null> {
    if (!(await this.isTauri())) return null
    try {
      return await invoke<string>(kind === 'data' ? 'open_data_folder' : 'open_works_folder')
    } catch (e) {
      this.error = String(e)
      return null
    }
  }
}
export const engine = new EngineClient()
