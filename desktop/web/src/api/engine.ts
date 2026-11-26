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

/** 后端字段名 → 中文提示用词 */
const FIELD_LABELS: Record<string, string> = {
  idea: '想法',
  template_id: '题材模板',
  prompt: '提示词',
  name: '名称',
  endpoint: '服务地址',
  model: '模型',
  message: '留言',
  shot_count: '镜头数',
  count: '数量',
  duration_s: '时长(秒)',
  version: '版本',
}

/**
 * 把 FastAPI 的 422 校验错误数组翻译成人话。
 * 例：[{type:'string_too_short',loc:['body','idea'],ctx:{min_length:10}}]
 *   → "「想法」至少要 10 个字"
 * 不翻译的话，界面上只会剩一句毫无信息量的 "422 引擎返回错误"。
 */
function describeValidationErrors(errors: any[]): string {
  const parts: string[] = []
  for (const e of errors) {
    const loc: string[] = Array.isArray(e?.loc) ? e.loc : []
    const field = loc.length ? String(loc[loc.length - 1]) : ''
    const label = FIELD_LABELS[field] || field
    const type = String(e?.type || '')
    const ctx = e?.ctx || {}

    if (type === 'string_too_short') {
      parts.push(`「${label}」至少要 ${ctx.min_length ?? 1} 个字`)
    } else if (type === 'string_too_long') {
      parts.push(`「${label}」最多 ${ctx.max_length ?? '—'} 个字`)
    } else if (type === 'missing') {
      parts.push(`缺少必填项「${label}」`)
    } else if (type.startsWith('string_')) {
      parts.push(`「${label}」格式不对`)
    } else if (type.includes('parsing') || type.includes('type')) {
      parts.push(`「${label}」格式不对`)
    } else if (e?.msg) {
      parts.push(String(e.msg))
    }
  }
  return parts.join('；')
}

class EngineClient {
  base = ''
  token = ''
  online = false
  error = ''
  /** 最近一次接口错误的结构化详情（code/message/hint/need/balance），
   *  供界面按错误类型给出正确出路（去设置 / 检查厂商额度）。 */
  lastError: { code?: string; message?: string; hint?: string; need?: number; balance?: number } = {}
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
      // 浏览器预览默认连 7420；可用 VITE_ENGINE_PORT 指向别的本地引擎（调试多实例）
      const port = Number((import.meta.env.VITE_ENGINE_PORT as string | undefined) || 7420)
      const base = `http://127.0.0.1:${port}`
      try {
        const h = await fetch(`${base}/health`, { cache: 'no-store' })
        if (h.ok) {
          const t = await fetch(`${base}/api/local-token`, { cache: 'no-store' })
          const j = await t.json()
          info = { running: true, port, token: j.token, base_url: base }
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
    if (!this.online) {
      // 必须记下原因：上层要靠它区分"引擎没连上"和"引擎没响应"，
      // 否则所有失败都会被说成同一句"未连接或未响应"。
      this.error = '本地引擎未连接，请先启动鲸鲨漫剧桌面应用'
      return null
    }
    try {
      const res = await fetch(this.base + path, {
        method: opts.method || 'GET',
        headers: { 'Content-Type': 'application/json', 'X-Local-Token': this.token },
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      })
      if (!res.ok) {
        // 把 FastAPI 的 {detail:{code,message,hint}} 变成人话，避免把原始 JSON 甩给用户
        let detail = ''
        try {
          const j = await res.json()
          const d = j?.detail
          if (Array.isArray(d)) {
            // FastAPI 请求校验错误：detail 是 [{type,loc,msg,ctx}] 数组
            detail = describeValidationErrors(d)
          } else {
            const obj = typeof d === 'string' ? { message: d } : (d || {})
            this.lastError = {
              code: obj.code,
              message: obj.message,
              hint: obj.hint,
              need: typeof obj.need === 'number' ? obj.need : undefined,
              balance: typeof obj.balance === 'number' ? obj.balance : undefined,
            }
            detail = obj.message || j?.message || ''
            if (obj.hint) detail += ` · ${obj.hint}`
          }
        } catch { /* 非 JSON 响应保留状态文本 */ }
        throw new Error(detail || `${res.status} 引擎返回错误`)
      }
      return (await res.json()) as T
    } catch (e) {
      const raw = String((e as Error).message || e)
      // fetch 抛的是英文 "Failed to fetch"，直接甩给用户等于没说是哪儿错了
      this.error = /failed to fetch|networkerror|load failed/i.test(raw)
        ? '引擎没有响应（可能正在重启或已退出）'
        : raw
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
