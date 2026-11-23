/**
 * 流式剧本的增量解析。
 *
 * 模型是逐字吐出 JSON 的：
 *   {"title":"平凡一百年","episodes":[{"idx":1,"title":"开学第一天哭全班","tags":[...],"script":"正文…"}]}
 *
 * 所以"实时看到一集一集长出来"不能靠等完整 JSON —— 必须从**残缺的 JSON**
 * 里增量抠出已经写好的部分：
 *   - 已经闭合的集 → 完整卡片
 *   - 正在写的那一集 → 显示已吐出的正文片段 + 光标
 *
 * 兜底：模型没按 JSON 输出时，退回按「第 N 集」标题切纯文本。
 */
export interface StreamEpisode {
  /** 集序号 */
  idx: number
  /** 集标题（可能还没吐出来） */
  title: string
  /** 正文（可能只写了一半） */
  body: string
  /** 是否是正在写的那一集（最后一段） */
  active: boolean
}
/** 反转义 JSON 字符串片段（流式过程中只有一半，转义要容错）。 */
function unescapeJson(s: string): string {
  return s
    .replace(/\\u([0-9a-fA-F]{4})/g, (_, h) => String.fromCharCode(parseInt(h, 16)))
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\r')
    .replace(/\\t/g, '\t')
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, '\\')
}
/** JSON 字符串内容（允许未闭合）：((?:[^"\\]|\\.)*) */
const JSTR = '((?:[^"\\\\]|\\\\.)*)'
/** 从残缺 JSON 里增量解析每一集。 */
function parseJsonEpisodes(text: string): StreamEpisode[] {
  // 每个 episode 对象的起点
  const marks: { idx: number; start: number }[] = []
  const re = /\{\s*"idx"\s*:\s*(\d+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    marks.push({ idx: parseInt(m[1], 10) || marks.length + 1, start: m.index })
  }
  if (!marks.length) return []
  const out: StreamEpisode[] = []
  for (let i = 0; i < marks.length; i++) {
    const seg = text.slice(marks[i].start, i + 1 < marks.length ? marks[i + 1].start : text.length)
    const tm = seg.match(new RegExp(`"title"\\s*:\\s*"${JSTR}"`))
    const sm = seg.match(new RegExp(`"script"\\s*:\\s*"${JSTR}`))
    const tmv = tm?.[1] ?? ''
    const smv = sm?.[1] ?? ''
    out.push({
      idx: marks[i].idx,
      title: tmv ? unescapeJson(tmv) : '',
      body: smv ? unescapeJson(smv) : '',
      active: i === marks.length - 1,
    })
  }
  return out
}
/** 匹配集标题行：第1集 / 第 1 集 / 第1集·标题 */
const EP_HEAD = /^第\s*([0-9]+|[一二三四五六七八九十百]+)\s*集\s*[·\.、:：\-—]?\s*(.*)$/
const CN_NUM: Record<string, number> = {
  一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10,
  十一: 11, 十二: 12, 十三: 13, 十四: 14, 十五: 15,
  二十: 20, 三十: 30, 四十: 40, 五十: 50, 六十: 60,
  七十: 70, 八十: 80, 九十: 90, 一百: 100,
}
/** 中文数字转阿拉伯（覆盖常见的 1-100 组合） */
function cnToNum(s: string): number {
  if (CN_NUM[s]) return CN_NUM[s]
  if (s.includes('十')) {
    const [head, tail] = s.split('十')
    return (head ? (CN_NUM[head] || 0) : 1) * 10 + (tail ? (CN_NUM[tail] || 0) : 0)
  }
  return 0
}
/** 兜底：按「第 N 集」标题切纯文本。 */
function parsePlainEpisodes(text: string): StreamEpisode[] {
  const lines = text.split('\n')
  const eps: StreamEpisode[] = []
  let cur: StreamEpisode | null = null
  let fallbackIdx = 0
  for (const raw of lines) {
    const line = raw.trim()
    const m = line.match(EP_HEAD)
    if (m && m[2].length <= 40) {
      const num = /^[0-9]+$/.test(m[1]) ? parseInt(m[1], 10) : cnToNum(m[1])
      fallbackIdx += 1
      cur = {
        idx: num > 0 ? num : fallbackIdx,
        title: m[2].replace(/^[·\.、:：\-—]\s*/, '').trim(),
        body: '',
        active: false,
      }
      eps.push(cur)
      continue
    }
    if (cur) cur.body += (cur.body ? '\n' : '') + raw
    else if (line) {
      cur = { idx: 1, title: '', body: raw, active: false }
      eps.push(cur)
    }
  }
  if (eps.length) eps[eps.length - 1].active = true
  return eps
}
/**
 * 把流式全文切成集。
 * 返回最后一项 active=true —— 它是"正在写"的那一集。
 */
export function parseStreamEpisodes(text: string): StreamEpisode[] {
  if (!text) return []
  if (/"episodes"\s*:/.test(text) || /"idx"\s*:/.test(text)) {
    const eps = parseJsonEpisodes(text)
    if (eps.length) return eps
  }
  return parsePlainEpisodes(text)
}
/** 从流式文本里提取"正在写第几集"，用于阶段提示。 */
export function currentEpisodeHint(text: string): { idx: number; title: string } | null {
  const eps = parseStreamEpisodes(text)
  if (!eps.length) return null
  const last = eps[eps.length - 1]
  return { idx: last.idx, title: last.title }
}
