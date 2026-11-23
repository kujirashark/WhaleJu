<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { useGenStore } from '@/stores/gen'
import { useUiStore } from '@/stores/ui'
import { useCallsStore } from '@/stores/calls'
import { engine } from '@/api/engine'
import { parseStreamEpisodes } from '@/utils/stream'
import CallLogPanel from './CallLogPanel.vue'
const router = useRouter()
const project = useProjectStore()
const gen = useGenStore()
const ui = useUiStore()
const calls = useCallsStore()
const step = computed(() => project.step)
const done = computed(() => gen.done)
const script = computed(() => project.script)
const shots = computed(() => project.shots)
const firstAsset = computed(() => {
  // 优先用引擎里落库的**镜头画面**（第 6 步生成的那些），定妆图不算成片画面
  const persisted = project.assets.find((a: any) => a.url && a.kind === 'shot')
    || project.assets.find((a: any) => a.url && a.kind !== 'character')
  if (persisted) return project.assetUrl(persisted.url)
  const live = gen.items.find((i: any) => i.status === 'done' && i.asset_ref)
  return live?.asset_ref || null
})
/** 全部镜头画面（第 7 步网格）：定妆图不算成片画面 */
const shotAssets = computed(() =>
  project.assets.filter((a: any) => a.url && (a.kind === 'shot' || a.kind === 'video')),
)
/**
 * 第 6 步的镜头清单。
 * 引擎的生成批次只在内存里，重启就没了 —— 素材其实已经落在库里。
 * 这里用 visibleItems() 合并两者：实时状态取内存，画面取数据库。
 */
const visibleShots = computed(() => {
  const live = gen.visibleItems() as any[]
  if (live.length) return live
  // 引擎没有批次时：直接用库里还原出来的镜头（画面 + 场景描述）
  return (gen.persisted || []) as any[]
})
/** 第 1 步单一状态：任何时刻只呈现一种状态的信息，避免空态/忙碌/失败文案同屏打架。
 *  忙碌优先于「已有剧本」：重新生成时旧剧本还在，但界面必须显示进行中，
 *  否则用户点「重新生成这一稿」看不到任何反应。 */
/** 角色定妆图地址：优先本机素材（永久有效），退回厂商链接（会过期）。 */
function roleImg(r: any): string {
  return project.assetUrl(r?.ref_url) || project.assetUrl(r?.remote_url)
}
const scriptState = computed<'empty' | 'busy' | 'error' | 'done'>(() => {
  if (project.contentBusy) return 'busy'
  // 失败优先于「已有剧本」：重新生成失败时旧稿还在，
  // 但界面必须先说失败，否则用户会以为"这次生成成功了"。
  if (project.contentError) return 'error'
  if (script.value?.episodes?.length) return 'done'
  return 'empty'
})
/** 失败时仍可翻看上一稿（用户要能对比，而不是被挡在门外） */
const showOldScript = ref(false)
/** 当前稿序号（界面不能写死"第一稿"） */
const scriptVerText = computed(() => project.scriptVer || 1)
/* ── 生成过程的实时呈现 ────────────────────────────────────────
 * 用户要的是"看着它写"：一集一集长出来、当前集高亮、能回看全过程。
 * 之前是 done 时把流式文本清空换成最终稿，整个过程一闪而过。 */
/** 流式文本切出的分集 */
const liveEps = computed(() => parseStreamEpisodes(project.streamText))
/** 回看区：把归档的生成过程重新切成集 */
const archiveEps = computed(() => parseStreamEpisodes(project.lastStream))
/** 回看区的剧名 */
const archiveTitle = computed(() => {
  const m = project.lastStream.match(/"title"\s*:\s*"((?:[^"\\]|\\.)*)"/)
  return m ? m[1] : ''
})
/** 项目目标集数：引擎按用户想法解析出来的（没说集数就是 1 集），界面不能写死 3 */
const targetEpisodes = computed(() => {
  const n = Number((project.detail as any)?.episode_count || 0)
  if (n > 0) return n
  return script.value?.episodes?.length || 1
})
/** 已经写好的集数 */
const writtenEpisodes = computed(() => script.value?.episodes?.length || 0)
/** 下一集该写第几集（逐集推进） */
const nextEpisodeIndex = computed(() => writtenEpisodes.value + 1)
/** 还有没有下一集要写 */
const canWriteMore = computed(() => nextEpisodeIndex.value <= targetEpisodes.value)
/** 一共要写几集（生成过程中的进度条也要按真实集数） */
const totalEpisodes = computed(() =>
  Math.max(targetEpisodes.value, liveEps.value.length, writtenEpisodes.value, 1),
)
/** 阶段标题：正在写第几集、叫什么 */
const liveStageTitle = computed(() => {
  const cur = liveEps.value[liveEps.value.length - 1]
  if (cur && cur.title) return `正在写第 ${cur.idx} 集《${cur.title}》`
  if (cur) return `正在写第 ${cur.idx} 集`
  if (project.streamStage) return '已连接文本模型，正在等它开口'
  return '正在写第一稿'
})
const liveStageSub = computed(() => {
  if (!liveEps.value.length) {
    // 推理模型首字可能要十几秒，必须告诉用户在等什么、等了多久
    const s = waitedSec.value
    const base = `已等待 ${s} 秒 · 首次生成通常需要 10-30 秒`
    return s >= 8 ? `${base}（推理模型要先思考，属正常）` : base
  }
  const done = liveEps.value.filter((e) => !e.active).length
  const total = totalEpisodes.value
  return done > 0
    ? `已写完 ${done} 集，共 ${total} 集 · 正在实时输出`
    : `共 ${total} 集 · 正在实时输出`
})
/** 等待首字的秒数：空白等待期必须有交代，否则用户以为卡死 */
const waitedSec = ref(0)
let waitTimer: ReturnType<typeof setInterval> | undefined
watch(
  () => project.contentBusy,
  (busy) => {
    if (busy) {
      waitedSec.value = 0
      if (waitTimer) clearInterval(waitTimer)
      waitTimer = setInterval(() => { waitedSec.value++ }, 1000)
    } else if (waitTimer) {
      clearInterval(waitTimer)
      waitTimer = undefined
    }
  },
  { immediate: true },
)
onUnmounted(() => { if (waitTimer) clearInterval(waitTimer) })
/** 流式容器：内容增长时自动滚到底部 */
const streamBox = ref<HTMLElement | null>(null)
watch(
  () => project.streamText,
  async () => {
    await nextTick()
    const el = streamBox.value
    if (el) el.scrollTop = el.scrollHeight
  },
)
const scriptPill = computed(() => ({
  done: { text: `第 ${script.value?.version || 1} 稿`, cls: 'p-ok' },
  busy: { text: '生成中', cls: 'p-info' },
  error: { text: '生成失败', cls: 'p-err' },
  empty: { text: '待生成', cls: 'p-off' },
}[scriptState.value]))
/** 是否有真实素材可导出（第 8 步前置条件） */
const hasMaterial = computed(() =>
  project.assets.length > 0 || gen.items.some((i: any) => i.status === 'done' && i.asset_ref),
)
/** 是否有可展示的模型调用日志 */
const hasCallLog = computed(() => calls.live.length > 0)
/** 本机能力（导出 mp4 需要 ffmpeg）：导出前要提前告诉用户 */
const sys = reactive({ ffmpeg: true })
async function loadSystem() {
  const r = await engine.api<{ ffmpeg: boolean }>('/api/system/capabilities')
  if (r && typeof r.ffmpeg === 'boolean') sys.ffmpeg = r.ffmpeg
}
function window_open(url: string) { window.open(url, '_blank', 'noopener,noreferrer') }
onMounted(async () => {
  await project.loadDetail()
  await loadSystem()
  // 刷新页面后恢复进行中的生成批次（进度在引擎里，不会丢）
  if (project.currentId) await gen.restore(project.currentId)
})
/* 流程动作全部交给聊天窗口（见 stores/agent.ts）：
 * 这里只保留"看内容"和"取产物"两类动作，生成/确认/推进一律由 agent 执行。 */
/** 正在重生成的镜头（避免重复点击） */
const regenBusy = ref('')
/**
 * 只重新生成这一个镜头。
 * 整批重跑等于白烧一轮额度；用户要的是"这张换一张"。
 */
async function regenShot(it: any) {
  const pid = project.currentId
  if (!pid || regenBusy.value) return
  regenBusy.value = it.shot_id
  try {
    const r = await gen.regenerateShot(pid, it.shot_id)
    if (r.ok) ui.toast(`第 ${it.shot_id.replace('s', '')} 镜已重新生成`)
    else ui.toast(r.error || '重新生成失败')
    // 素材变了，项目的真实素材列表也要跟着刷新
    await project.loadDetail()
  } finally {
    regenBusy.value = ''
  }
}
/* ── 第 5 步：分镜可以单独编辑、调整、增删 ──────────────────────────
 * 用户要的是"分镜表能改"：改某一镜的描述、调整重要度、挪位置、加一镜、删一镜。
 * 每个镜头有稳定 key，改动后素材关联不串台（引擎负责）。 */
/** 正在编辑的镜头 key（空 = 没在编辑） */
const editingShot = ref('')
const editScene = ref('')
const editImportance = ref<'key' | 'transition'>('transition')
const shotBusy = ref(false)
/** 改了描述但画面还是旧的镜头（引擎事实，刷新后仍在） */
const staleShots = computed<Set<string>>(() => {
  const s = new Set<string>()
  for (const it of (gen.persisted || []) as any[]) {
    if (it.status === 'edited') s.add(it.shot_id)
  }
  return s
})
/** 分镜表（引擎权威数据） */
const shotPlan = computed<any[]>(() => shots.value?.shots || [])
function startEditShot(s: any) {
  editingShot.value = s.key
  editScene.value = s.scene || ''
  editImportance.value = s.importance === 'key' ? 'key' : 'transition'
}
function cancelEditShot() {
  editingShot.value = ''
}
async function saveShot(s: any) {
  if (!editScene.value.trim()) { ui.toast('场景描述不能为空'); return }
  shotBusy.value = true
  try {
    const r = await project.updateShot(s.key, {
      scene: editScene.value.trim(), importance: editImportance.value,
    })
    if (!r.ok) { ui.toast(r.error || '保存失败'); return }
    editingShot.value = ''
    // 刷新镜头清单：拿到"待重生成"标记（引擎事实）
    if (project.currentId) await gen.loadPersisted(project.currentId)
    if (r.stale?.length) ui.toast('已保存。重新生成这一镜才会用新描述', 4000)
    else ui.toast('分镜已保存')
  } finally {
    shotBusy.value = false
  }
}
/** 挪位置：把这一镜移到第 n 位 */
async function moveShot(s: any, dir: -1 | 1) {
  const target = (s.idx || 0) + dir
  if (target < 1 || target > shotPlan.value.length) return
  shotBusy.value = true
  try {
    const r = await project.updateShot(s.key, { idx: target })
    if (!r.ok) ui.toast(r.error || '调整顺序失败')
  } finally {
    shotBusy.value = false
  }
}
/** 新增一镜 */
async function doAddShot() {
  const scene = window.prompt('新镜头拍什么？', '新镜头：')
  if (scene === null) return
  if (!scene.trim()) { ui.toast('场景描述不能为空'); return }
  shotBusy.value = true
  try {
    const r = await project.addShot(scene.trim())
    if (!r.ok) ui.toast(r.error || '新增失败')
    else ui.toast('已加一镜')
  } finally {
    shotBusy.value = false
  }
}
/** 删一镜（连同它已生成的画面） */
async function doDeleteShot(s: any) {
  if (!window.confirm(`删掉第 ${s.idx} 镜？\n「${s.scene || '（无描述）'}」\n它已经生成的画面也会一起删掉。`)) return
  shotBusy.value = true
  try {
    const r = await project.deleteShot(s.key)
    if (!r.ok) ui.toast(r.error || '删除失败')
    else {
      if (project.currentId) await gen.loadPersisted(project.currentId)
      ui.toast('已删掉这一镜')
    }
  } finally {
    shotBusy.value = false
  }
}
/** 体积格式化：用户看得懂的 MB / GB。 */
function prettySize(n?: number | null): string {
  const b = Number(n || 0)
  if (b <= 0) return '—'
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`
  return `${(b / 1024 / 1024 / 1024).toFixed(2)} GB`
}
/**
 * 下载成片：走引擎的只读下载端点。
 * 之前这个按钮只"打开文件夹"，用户点完什么也没拿到。
 */
function downloadWork() {
  const r = project.expResult
  if (!r?.work_id) { ui.toast('还没有可下载的成片'); return }
  const url = `${engine.base}/api/works/${r.work_id}/download?token=${engine.token}`
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
  ui.toast('开始下载成片')
}
/** 第 7 步确认这一版：推进引擎状态（CP3_PENDING → DELIVER），再进导出。 */
</script>
<template>
  <div class="who">
    <div class="av">
      <svg width="16" height="13" viewBox="0 0 48 40" fill="none" aria-hidden="true"><path d="M9 27C11 16.5 17 7.5 26 5c3.4-.9 6 .8 6 4.4V27Z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M4 33.5q4-3.5 8.5 0t8.5 0t8.5 0t8.5 0t6.5 0" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>
    </div>
    <div class="card">
      <!-- 第 1 步：四种状态互斥，一次只说一件事 -->
      <template v-if="step === 0">
        <div class="card-hd">第 1 步 · 写剧本<span class="pill" :class="scriptPill.cls">{{ scriptPill.text }}</span></div>
        <div class="card-bd">
          <!-- 生成中：阶段提示 + 分集实时渲染，不给无关操作 -->
          <template v-if="scriptState === 'busy'">
            <!-- 厂商限流退避：把等待讲明白，否则用户以为卡死 -->
            <div v-if="project.streamWait" class="wait-box">
              <span class="busy-dot"></span>
              <div>
                <div class="gen-live-t">{{ project.streamWait.reason }}，正在自动重试</div>
                <div class="gen-live-s">
                  第 {{ project.streamWait.attempt }} / {{ project.streamWait.max_attempts }} 次 ·
                  {{ project.streamWait.wait_s }} 秒后再试 · 厂商额度恢复后会自动继续
                </div>
              </div>
            </div>
            <div v-else class="gen-live">
              <span class="busy-dot"></span>
              <div style="flex:1;min-width:0">
                <div class="gen-live-t">{{ liveStageTitle }}</div>
                <div class="gen-live-s">{{ liveStageSub }}</div>
              </div>
              <div v-if="liveEps.length" class="gen-ep-progress">
                <span v-for="n in totalEpisodes" :key="n" class="pip" :class="{ on: n <= liveEps.length }"></span>
              </div>
            </div>
            <!-- 分集实时渲染：一集一集长出来，当前集高亮 -->
            <div v-if="liveEps.length" ref="streamBox" class="stream-ep">
              <div v-for="(ep, i) in liveEps" :key="i" class="s-ep" :class="{ active: ep.active }">
                <div class="s-ep-hd">
                  <span class="s-ep-no">第 {{ ep.idx }} 集</span>
                  <span v-if="ep.title" class="s-ep-title">{{ ep.title }}</span>
                  <span v-if="ep.active" class="s-ep-live"><span class="busy-dot"></span>正在写</span>
                </div>
                <div v-if="ep.body" class="s-ep-bd">{{ ep.body }}</div>
                <div v-else-if="ep.active" class="s-ep-skel">
                  <i></i><i></i><i></i>
                </div>
              </div>
              <span class="caret">▍</span>
            </div>
            <!-- 首字未到：骨架屏占位，避免整块内容突然跳出来 -->
            <div v-else ref="streamBox" class="stream-ep">
              <div v-for="n in totalEpisodes" :key="n" class="s-ep">
                <div class="s-ep-hd"><span class="s-ep-no s-ep-no skel"></span></div>
                <div class="s-ep-skel"><i></i><i></i><i></i></div>
              </div>
            </div>
          </template>
          <!-- 生成失败：说清原因 + 给出路 -->
          <template v-else-if="scriptState === 'error'">
            <div class="state-t">这次没生成成功</div>
            <div class="hint-warn">{{ project.contentError }}</div>
            <div class="acts">
              <button v-if="script?.episodes?.length" class="btn btn-s" @click="showOldScript = !showOldScript">
                {{ showOldScript ? '收起上一稿' : `看看上一稿（第 ${scriptVerText} 稿）` }}
              </button>
            </div>
            <div class="chat-hint">在下方聊天框说「重新生成这一稿」，我就重写一遍。</div>
            <!-- 上一稿仍然保留，只是这次没写出来 -->
            <div v-if="showOldScript && script?.episodes?.length" class="script old-script">
              <div class="old-tag">上一稿（未改动）</div>
              <template v-for="(ep, i) in script.episodes" :key="i">
                <p><b>第 {{ ep.idx || i + 1 }} 集 · {{ ep.title }}</b></p>
                <p>{{ ep.script }}</p>
              </template>
            </div>
          </template>
          <!-- 空态：一句话说明 + 一个主动作 -->
          <template v-else-if="scriptState === 'empty'">
            <p>
              根据这个项目想法，用你配置的文本模型写一部
              <b>{{ targetEpisodes }} 集</b>竖屏短剧<template v-if="targetEpisodes > 1">（一次写一集，省额度也少被限流）</template>。
            </p>
            <div class="chat-hint">在下方聊天框说「写剧本」，我就用你配置的文本模型开始写。</div>
            <div class="note">还没配置模型？在聊天框说「去配置模型」，我带你去设置。</div>
          </template>
          <!-- 已完成 -->
          <template v-else>
            <!-- 模型这次没写完：已保住写完的那几集，但必须说清这一稿不全 -->
            <div v-if="project.partial" class="hint-warn">
              模型这次写到一半就断了，已保住写完的 {{ script.episodes.length }} 集。
              点「重新生成」可以再试一次。
            </div>
            <p>
              第 {{ scriptVerText }} 稿已写好，
              <template v-if="targetEpisodes > 1">
                已写 <b>{{ writtenEpisodes }}</b> / {{ targetEpisodes }} 集，已保存到本机。
              </template>
              <template v-else>共 {{ writtenEpisodes }} 集，已保存到本机。</template>
            </p>
            <!-- 刚生成的过程可回看：用户能确认模型确实写了一篇完整稿 -->
            <details v-if="project.lastStream" class="stream-archive">
              <summary>看看模型刚才是怎么写出来的</summary>
              <div class="stream-ep archive">
                <div v-if="archiveTitle" class="s-ep-hd"><span class="s-ep-no">剧名</span><span class="s-ep-title">{{ archiveTitle }}</span></div>
                <div v-for="(ep, i) in archiveEps" :key="i" class="s-ep">
                  <div class="s-ep-hd">
                    <span class="s-ep-no">第 {{ ep.idx }} 集</span>
                    <span v-if="ep.title" class="s-ep-title">{{ ep.title }}</span>
                  </div>
                  <div v-if="ep.body" class="s-ep-bd">{{ ep.body }}</div>
                </div>
              </div>
            </details>
            <div class="script" style="margin-top:14px">
              <template v-for="(ep, i) in script.episodes" :key="i">
                <p><b>第 {{ ep.idx || i + 1 }} 集 · {{ ep.title }}</b></p>
                <p>{{ ep.script }}</p>
              </template>
            </div>
            <div class="chat-hint">
              在下方聊天框说「确认剧本」我就往下走，说「继续写第 {{ nextEpisodeIndex }} 集」我就接着写下一集，说「重新生成这一稿」我就重写。
            </div>
          </template>
          <!-- 模型调用日志：生成结束后依然保留，便于回看这次到底调了什么 -->
          <CallLogPanel v-if="hasCallLog" />
        </div>
      </template>
      <!-- 第 2 步：确认剧本 —— 所见即所得，直接看完整正文 -->
      <template v-else-if="step === 1">
        <div class="card-hd">第 2 步 · 确认剧本<span class="pill" :class="project.status === 'CP1_PENDING' ? 'p-wait' : 'p-ok'">{{ project.status === 'CP1_PENDING' ? '等你确认' : '已确认' }}</span></div>
        <div class="card-bd">
          <p>看看故事走向对不对。内容是刚生成的真实剧本。</p>
          <div v-if="script?.episodes?.length" style="margin-top:10px">
            <!-- 分集大纲 -->
            <div v-for="(ep, i) in script.episodes" :key="i" class="ep">
              <span class="no">EP.{{ String(ep.idx || i + 1).padStart(2, '0') }}</span>
              <div><h5>{{ ep.title }}</h5><div class="tags"><span v-for="(t, j) in (ep.tags || [])" :key="j" class="tag">{{ t }}</span></div></div>
            </div>
            <!-- 正文全文：确认前就要看清每一句在讲什么 -->
            <div class="script" style="margin-top:14px">
              <template v-for="(ep, i) in script.episodes" :key="'body-' + i">
                <p><b>第 {{ ep.idx || i + 1 }} 集 · {{ ep.title }}</b></p>
                <p>{{ ep.script }}</p>
              </template>
            </div>
          </div>
          <div v-else class="hint-warn">还没有剧本，请先回到第 1 步生成。</div>
          <div class="chat-hint">
            在下方聊天框说「确认剧本」，我就去定角色；说「回去改剧本」我就回到第 1 步。
          </div>
        </div>
      </template>
      <!-- 第 3 步 -->
      <template v-else-if="step === 2">
        <div class="card-hd">第 3 步 · 角色形象<span class="pill p-info">{{ project.characters.length }} 个角色</span></div>
        <div class="card-bd">
          <template v-if="project.characters.length">
            <p>由你配置的图片模型生成的定妆图，选中的会用在全部镜头里。</p>
            <div class="rolegrid">
              <div v-for="r in project.characters" :key="r.id" class="role" :class="{ sel: project.selectedRoles.has(r.id) }" @click="project.toggleRole(r.id)">
                <img v-if="roleImg(r)" :src="roleImg(r)" :alt="`${r.name}的定妆图`" loading="lazy">
                <div v-else class="role-ph">无图</div>
                <span class="chk"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#04121c" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>
                <span class="lab">{{ r.name }}</span>
              </div>
            </div>
            <div v-if="project.contentBusy" class="gen-live" style="margin-top:12px">
              <span class="busy-dot"></span>
              <div>
                <div class="gen-live-t">正在重新生成 5 张角色定妆图</div>
                <div class="gen-live-s">图片模型逐张出图，通常需要十几到几十秒 · 已等待 {{ waitedSec }} 秒</div>
              </div>
            </div>
            <div class="chat-hint">
              在下方聊天框说「确认角色形象」，我就锁定这些形象往下走；说「重新生成定妆图」我就重出图。
            </div>
            <div class="note">定妆图由你配置的图片模型生成，生成后会自动存到本机，链接过期也不会变裂图。</div>
          </template>
          <template v-else>
            <p>还没有定妆图。用你在设置里配置的图片模型生成角色形象。</p>
            <div v-if="project.contentError" class="hint-warn">{{ project.contentError }}</div>
            <!-- 生成中：说明在做什么、等多久，避免"点了没反应" -->
            <div v-if="project.contentBusy" class="gen-live" style="margin-top:12px">
              <span class="busy-dot"></span>
              <div>
                <div class="gen-live-t">正在生成 5 张角色定妆图</div>
                <div class="gen-live-s">图片模型逐张出图，通常需要十几到几十秒 · 已等待 {{ waitedSec }} 秒</div>
              </div>
            </div>
            <div class="chat-hint">
              在下方聊天框说「生成定妆图」，我就用你的图片模型出图；说「去配置图片模型」我带你去设置。
            </div>
            <div class="note">没有配置图片模型时，这里不会显示任何假角色脸。</div>
          </template>
        </div>
      </template>
      <!-- 第 4 步 -->
      <template v-else-if="step === 3">
        <div class="card-hd">第 4 步 · 确认角色形象<span class="pill" :class="project.rolesLocked ? 'p-ok' : 'p-wait'">{{ project.rolesLocked ? '已确认' : '等你确认' }}</span></div>
        <div class="card-bd">
          <p>这 {{ project.selectedRoles.size }} 个形象会固定在镜头里。现在是：</p>
          <div class="rolegrid" style="margin-top:10px">
            <div v-for="r in project.characters.filter((c:any) => project.selectedRoles.has(c.id))" :key="r.id" class="role">
              <img v-if="roleImg(r)" :src="roleImg(r)" :alt="r.name" loading="lazy"><div v-else class="role-ph">无图</div>
              <span class="lab">{{ r.name }}{{ project.rolesLocked ? ' · 已确认' : '' }}</span>
            </div>
          </div>
          <div v-if="!project.selectedRoles.size" class="hint-warn">还没有选中的角色，请先回第 3 步生成并选择。</div>
          <div class="chat-hint">
            在下方聊天框说「确认角色形象」，我就锁定这些形象并往下走；说「重新生成定妆图」我就重出图。
          </div>
          <div class="note w">确认后想换形象，需要把已经做好的镜头重新生成一遍。建议先确认再继续。</div>
        </div>
      </template>
      <!-- 第 5 步 -->
      <template v-else-if="step === 4">
        <div class="card-hd">第 5 步 · 拆分镜头<span class="pill p-info">{{ shotPlan.length }} 个镜头</span></div>
        <div class="card-bd">
          <template v-if="shotPlan.length">
            <p>由你配置的文本模型拆分，共 <b>{{ shotPlan.length }}</b> 个镜头，已保存到本机。<b>每一镜都可以单独改</b>。</p>
            <!-- 分镜表：可编辑、可调整、可增删 -->
            <div class="shot-plan">
              <div v-for="s in shotPlan" :key="s.key" class="sp-row" :class="{ editing: editingShot === s.key }">
                <div class="sp-no">{{ s.idx }}</div>
                <!-- 普通态：只读展示 -->
                <template v-if="editingShot !== s.key">
                  <div class="sp-main">
                    <div class="sp-scene">
                      {{ s.scene }}
                      <span v-if="staleShots.has(s.key)" class="chip c-wait" title="描述已改，重新生成这一镜才会生效">待重生成</span>
                    </div>
                    <div class="sp-tag">
                      <span class="chip" :class="s.importance === 'key' ? 'c-key' : 'c-wait'">{{ s.importance === 'key' ? '重要' : '过渡' }}</span>
                    </div>
                  </div>
                  <div class="sp-ops">
                    <button class="btn btn-s" @click="startEditShot(s)">编辑</button>
                    <button class="btn btn-s" :disabled="shotBusy || s.idx <= 1" @click="moveShot(s, -1)" title="上移">↑</button>
                    <button class="btn btn-s" :disabled="shotBusy || s.idx >= shotPlan.length" @click="moveShot(s, 1)" title="下移">↓</button>
                    <button class="btn btn-s sp-del" :disabled="shotBusy" @click="doDeleteShot(s)" title="删掉这一镜">删</button>
                  </div>
                </template>
                <!-- 编辑态：行内改描述与重要度 -->
                <template v-else>
                  <div class="sp-main">
                    <textarea
                      v-model="editScene"
                      class="sp-input"
                      rows="3"
                      placeholder="这一镜拍什么？写得越具体，生成越准"
                      aria-label="镜头场景描述"></textarea>
                    <div class="sp-imp">
                      <label class="sp-radio">
                        <input type="radio" value="key" v-model="editImportance"> 重要镜头（画质优先）
                      </label>
                      <label class="sp-radio">
                        <input type="radio" value="transition" v-model="editImportance"> 过渡镜头（成本优先）
                      </label>
                    </div>
                  </div>
                  <div class="sp-ops">
                    <button class="btn btn-p" :disabled="shotBusy" @click="saveShot(s)">保存</button>
                    <button class="btn btn-s" :disabled="shotBusy" @click="cancelEditShot">取消</button>
                  </div>
                </template>
              </div>
            </div>
            <div class="acts">
              <button class="btn btn-s" :disabled="shotBusy" @click="doAddShot">+ 加一个镜头</button>
              <span style="font-size:11px;color:var(--ink3);font-family:var(--mono)">改动已保存到本机</span>
            </div>
            <div class="chat-hint">
              在下方聊天框说「生成画面」，我就按这个方案开跑；说「重新拆镜头」我就重拆。
            </div>
            <div class="note">
              预计生成 {{ shotPlan.length }} 张画面，每张 1.5 额度，共约
              {{ Math.round(shotPlan.length * 1.5 * 10) / 10 }} 额度；
              用你自己的 API 密钥则不消耗平台额度。生成失败不计费。
            </div>
            <div v-if="gen.lastError" class="hint-warn">
              <div><b>没能开始生成：</b>{{ gen.lastError }}</div>
              <div class="acts" style="margin-top:10px">
                <button v-if="gen.lastErrorCode === 'E2001'" class="btn btn-p" @click="ui.payOpen = true">充值额度</button>
                <button class="btn btn-s" @click="router.push('/settings')">去设置生成视频</button>
              </div>
              <div v-if="gen.lastErrorHint" style="margin-top:8px">{{ gen.lastErrorHint }}</div>
            </div>
            <div class="note">生成前会检查对应的模型是否已配置并测通；未配置不会扣钱也不会伪造画面。</div>
          </template>
          <template v-else>
            <p>还没有镜头表。先由文本模型根据剧本拆分镜头。</p>
            <div v-if="project.contentError" class="hint-warn">{{ project.contentError }}</div>
            <!-- 拆分中：说明在做什么、等多久 -->
            <div v-if="project.contentBusy" class="gen-live" style="margin-top:12px">
              <span class="busy-dot"></span>
              <div>
                <div class="gen-live-t">正在按剧情拆分 12 个镜头</div>
                <div class="gen-live-s">文本模型正在切分场景，通常需要几秒到十几秒 · 已等待 {{ waitedSec }} 秒</div>
              </div>
            </div>
            <div class="chat-hint">
              在下方聊天框说「拆镜头」，我就用文本模型拆；说「回去写剧本」我就回到第 1 步。
            </div>
            <div class="note">没有镜头表时不会显示任何假镜头。</div>
          </template>
        </div>
      </template>
      <!-- 第 6 步 -->
      <template v-else-if="step === 5">
        <div class="card-hd">第 6 步 · 生成画面<span class="pill" :class="gen.total && done >= gen.total ? 'p-ok' : 'p-info'">{{ done }} / {{ gen.total || '—' }}</span></div>
        <div class="card-bd">
          <p>{{ gen.total && done >= gen.total ? '镜头都好了，可以看成片。' : '生成进度全部来自本机引擎的真实任务状态。' }}</p>
          <p v-if="gen.total" style="font-size:12px;color:var(--ink3)">
            本批次用{{ gen.ability === 'video' ? '视频' : '图片' }}模型逐个镜头生成，
            每镜 {{ gen.unitPrice }} 额度，共 {{ gen.estimatedCost }} 额度<template v-if="gen.billing === 'own_key'">（用你自己的密钥，不扣平台额度）</template>。
          </p>
          <div class="progress"><i v-for="n in (gen.total || 12)" :key="n" :class="{ on: n <= done }"></i></div>
          <div style="display:flex;justify-content:space-between;align-items:baseline">
            <span class="big-num">{{ gen.total ? Math.round(done / gen.total * 100) : 0 }}%</span>
            <span style="font-size:11px;color:var(--ink3);font-family:var(--mono)">已完成 {{ done }} 个 · 失败 {{ gen.failed }} 个（不计费）<template v-if="gen.eta"> · 约 {{ gen.eta }} 秒</template></span>
          </div>
          <!-- 镜头卡片：每个镜头都看得到真实画面（图片/视频），并能单独重生成。
               数据源是引擎的持久化素材（visibleItems），
               引擎重启/刷新页面后画面依然在，不会变成一片空白。 -->
          <div class="shot-grid">
            <div v-for="(it, idx) in visibleShots" :key="it.shot_id" class="shot-card" :class="it.status">
              <div class="shot-thumb">
                <video v-if="it.media_url && it.kind === 'video'"
                       :src="project.assetUrl(it.media_url)"
                       controls muted playsinline preload="metadata"
                       @click.stop></video>
                <img v-else-if="it.media_url" :src="project.assetUrl(it.media_url)"
                     :alt="`第 ${idx + 1} 镜：${it.scene_desc}`" loading="lazy"
                     @click.stop="window_open(project.assetUrl(it.media_url))">
                <div v-else class="shot-ph">
                  <span v-if="it.status === 'running'" class="busy-dot"></span>
                  <span v-else>{{ idx + 1 }}</span>
                </div>
                <span class="shot-no">第 {{ idx + 1 }} 镜</span>
                <span v-if="it.status === 'running'" class="shot-badge c-run">生成中</span>
                <span v-else-if="it.status === 'failed'" class="shot-badge c-fail">失败</span>
                <span v-else-if="it.status === 'edited'" class="shot-badge c-wait">待重生成</span>
              </div>
              <div class="shot-meta">
                <div class="t">{{ it.scene_desc || `第 ${idx + 1} 镜` }}</div>
                <div class="s">
                  <template v-if="it.status === 'edited'">描述已改，点「重新生成」才会用新描述</template>
                  <template v-else-if="it.status === 'done'">已生成 · {{ it.kind === 'video' ? '视频' : '图片' }}</template>
                  <template v-else-if="it.status === 'running'">正在生成…</template>
                  <template v-else-if="it.status === 'failed'">{{ it.fail_reason || '生成失败' }}（不计费）</template>
                  <template v-else>排队中</template>
                </div>
              </div>
              <button class="btn btn-s shot-regen" :disabled="regenBusy === it.shot_id" @click="regenShot(it)">
                {{ regenBusy === it.shot_id ? '重生成中…' : '重新生成' }}
              </button>
            </div>
          </div>
          <div v-if="gen.fatalReason" class="hint-warn">
            <div><b>生成已停下：</b>{{ gen.fatalReason }}</div>
            <div class="acts" style="margin-top:10px">
              <button class="btn btn-p" @click="router.push('/settings')">去设置生成视频</button>
            </div>
            <div style="margin-top:8px">剩下的镜头没有执行，也没有扣任何额度。</div>
          </div>
            <div v-if="gen.notStarted" class="hint-warn">还没有开始生成。在下方聊天框说「生成画面」我就开跑；这里只显示引擎的真实进度，没有演示动画。</div>
          <div v-if="gen.lastError" class="hint-warn">
            <div><b>生成没跑起来：</b>{{ gen.lastError }}</div>
            <div class="acts" style="margin-top:10px">
              <button v-if="gen.lastErrorCode === 'E2001'" class="btn btn-p" @click="ui.payOpen = true">充值额度</button>
              <button class="btn btn-s" @click="router.push('/settings')">去设置生成视频</button>
            </div>
            <div v-if="gen.lastErrorHint" style="margin-top:8px">{{ gen.lastErrorHint }}</div>
          </div>
          <div class="acts">
            <template v-if="done < gen.total && gen.total">
              <button class="btn btn-p" @click="gen.paused ? gen.resume(project.currentId || '') : gen.pause(project.currentId || ''); ui.toast(gen.paused ? '已继续生成' : '已暂停，进度已保存')">{{ gen.paused ? '继续生成' : '暂停生成' }}</button>
              <span class="chip c-wait">真实生成中 · 引擎按镜头推进</span>
            </template>
          </div>
          <div class="chat-hint">
            在下方聊天框说「生成画面」我就开跑，说「确认这一版」我就去导出。
          </div>
          <div class="note">生成在本机引擎里进行，关掉页面不会中断；引擎重启后需要重新生成，已经做好的画面仍然在。</div>
        </div>
      </template>
      <!-- 第 7 步：素材取自引擎 assets（刷新后仍在），不是内存态 -->
      <template v-else-if="step === 6">
        <div class="card-hd">第 7 步 · 看成片<span class="pill p-info">{{ visibleShots.length }} 段素材</span></div>
        <div class="card-bd">
          <template v-if="visibleShots.length">
            <p>这是模型真实生成的画面。点开看大图；不满意在第 6 步单独重生成对应镜头。</p>
            <!-- 全部镜头画面：能一眼看完这一集 -->
            <div class="shot-grid">
              <div v-for="(it, idx) in visibleShots" :key="it.shot_id" class="shot-card">
                <div class="shot-thumb">
                  <video v-if="it.media_url && it.kind === 'video'" :src="project.assetUrl(it.media_url)" controls muted playsinline preload="metadata"></video>
                  <img v-else-if="it.media_url" :src="project.assetUrl(it.media_url)" :alt="`第 ${idx + 1} 镜`" loading="lazy" @click="window_open(project.assetUrl(it.media_url))">
                  <div v-else class="shot-ph">{{ idx + 1 }}</div>
                  <span class="shot-no">第 {{ idx + 1 }} 镜</span>
                </div>
                <div class="shot-meta"><div class="t">{{ it.scene_desc || `第 ${idx + 1} 镜` }}</div></div>
              </div>
            </div>
            <div class="acts" style="justify-content:center">
              <button v-if="visibleShots[0].media_url" class="btn btn-s" @click="window_open(project.assetUrl(visibleShots[0].media_url))">在新窗口查看</button>
            </div>
            <div class="chat-hint" style="justify-content:center">
              在下方聊天框说「确认这一版」，我就去导出成片；说「重新生成画面」我就重跑镜头。
            </div>
            <div class="note">画面来自你配置的图片模型；没有真实素材时不会显示任何示例画面。</div>
          </template>
          <template v-else>
            <p>还没有真实画面。需要先完成生成，模型返回素材后这里才会显示。</p>
            <div class="chat-hint" style="justify-content:center">
              在下方聊天框说「生成画面」，我就开始跑。
            </div>
            <div class="note">这里不会用示例剧照冒充成片。</div>
          </template>
        </div>
      </template>
      <!-- 第 8 步 -->
      <template v-else>
        <div class="card-hd">第 8 步 · 导出视频<span class="pill" :class="project.exp.state === 'done' ? 'p-ok' : 'p-off'">{{ project.exp.state === 'done' ? '已导出' : project.exp.state === 'running' ? '导出中' : '未开始' }}</span></div>
        <div class="card-bd">
          <p>导出设置好就可以发。默认竖屏 1080 × 1920，画面不带任何水印。</p>
          <div v-if="!hasMaterial" class="hint-warn" style="margin-top:12px">
            还没有真实画面可导出。完成第 6 步生成后，这里才能导出成片。
          </div>
          <div v-if="hasMaterial && sys.ffmpeg === false" class="hint-warn" style="margin-top:12px">
            本机没有找到可用的 ffmpeg：画面能正常生成，但合成 mp4 需要它。
            装好后会自动识别；也可以在系统环境变量 <code>WHALESHARK_FFMPEG</code> 里
            写上 ffmpeg.exe 的完整路径。现在导出仍可用，会给你一份画面素材包。
          </div>
          <div style="margin-top:12px;display:flex;flex-direction:column;gap:7px">
            <div class="ch" :class="{ sel: project.ratio === 'v' }" @click="project.ratio = 'v'"><span class="rad"></span><div><div class="t">竖屏 1080 × 1920</div><div class="d">适合抖音、视频号</div></div><span class="pr">MP4</span></div>
            <div class="ch" :class="{ sel: project.ratio === 'h' }" @click="project.ratio = 'h'"><span class="rad"></span><div><div class="t">横屏 1920 × 1080</div><div class="d">适合 B 站、YouTube</div></div><span class="pr">MP4</span></div>
          </div>
          <div v-if="project.exp.state === 'running'" class="progress solid" style="margin-top:16px"><i :style="{ width: `${project.exp.pct}%` }"></i></div>
          <!-- 真实产物：格式、体积、时长都来自引擎实际写出的文件 -->
          <div v-if="project.exp.state === 'done' && project.expResult" class="exp-card">
            <!-- 导完就能看：不用先下载再打开 -->
            <video v-if="project.expResult.format === 'mp4' && project.expResult.preview_url"
                   class="work-preview"
                   :src="project.assetUrl(project.expResult.preview_url)"
                   controls playsinline preload="metadata"></video>
            <div class="exp-hd">
              <span class="dot" :class="project.expResult.format === 'mp4' ? 'ok' : 'warn'"></span>
              {{ project.expResult.format === 'mp4' ? '成片已生成' : '画面素材包已导出' }}
            </div>
            <div class="exp-row">
              <span>文件</span>
              <span>{{ project.expResult.format === 'mp4' ? 'MP4 视频' : `PNG 画面 ${project.expResult.frames || 0} 张` }}</span>
            </div>
            <div class="exp-row">
              <span>大小</span>
              <span>{{ prettySize(project.expResult.size_bytes) }}</span>
            </div>
            <div class="exp-row">
              <span>规格</span>
              <span>{{ project.expResult.ratio === '16:9' ? '横屏 1920 × 1080' : '竖屏 1080 × 1920' }}</span>
            </div>
            <div v-if="project.expResult.needs_ffmpeg" class="exp-warn">
              本机没找到 ffmpeg，合成 mp4 那一步跳过了 —— 给你的是原始画面 + 合成命令，
              装好 ffmpeg 后在聊天框说「重新导出」就能直接出片。
            </div>
          </div>
          <div class="acts">
            <template v-if="project.exp.state === 'done'">
              <button class="btn btn-p" @click="downloadWork">下载成片</button>
              <button class="btn btn-s" @click="router.push('/works')">去作品库</button>
              <button class="btn btn-s" @click="engine.openFolder('works'); ui.toast('已打开作品库文件夹')">打开文件夹</button>
            </template>
            <span style="font-size:11px;color:var(--ink3);font-family:var(--mono)">只导出本机真实生成的素材</span>
          </div>
          <div class="chat-hint">
            在下方聊天框说「导出成片」，我就合成竖屏 MP4。
          </div>
          <div class="note">画面干净不带水印；「本视频由 AI 生成」的声明会写进成片元数据与发布文案，发布时按平台要求勾选 AI 生成选项即可。</div>
        </div>
      </template>
    </div>
  </div>
</template>
