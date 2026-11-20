<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { useGenStore } from '@/stores/gen'
import { useUiStore } from '@/stores/ui'
import { engine } from '@/api/engine'
const router = useRouter()
const project = useProjectStore()
const gen = useGenStore()
const ui = useUiStore()
const step = computed(() => project.step)
const done = computed(() => gen.done)
const script = computed(() => project.script)
const shots = computed(() => project.shots)
const firstAsset = computed(() => gen.items.find((i: any) => i.status === 'done' && i.asset_ref)?.asset_ref || null)
function window_open(url: string) { window.open(url, '_blank', 'noopener,noreferrer') }
onMounted(() => project.loadDetail())
async function doGenScript() {
  const version = project.script ? project.scriptVer + 1 : 1
  const r = await project.genScriptStream(version)
  if (r.ok) ui.toast('剧本已由你配置的模型生成并保存到本机')
  else ui.toast(r.error || '生成失败，请检查文本模型配置')
}
async function doGenShots() {
  const r = await project.genShots(12)
  if (r.ok) ui.toast('镜头表已由你配置的模型生成')
  else ui.toast(r.error || '拆分失败，请检查文本模型配置')
}
function confirmRoles() {
  project.goto(3)
  ui.toast('已确认角色，下一步拆分镜头')
}
async function startGen() {
  const r = await gen.start(project.currentId || '', 12)
  if (r.ok) { project.goto(5); ui.toast(`已开始真实生成：${gen.routeReason || '按重要性分配'}`) }
  else ui.toast(r.hint || r.error || '无法开始生成')
}
async function doExport() {
  const work = await project.exportWork()
  if (work) {
    project.exp = { state: 'done', pct: 100 }
    ui.toast('成片已存入本机作品库（AI 标识已自动写入）')
  } else {
    project.exp = { state: 'idle', pct: 0 }
    ui.toast(engine.error || '导出失败：请确认已完成真实生成')
  }
}
</script>
<template>
  <div class="who">
    <div class="av">
      <svg width="16" height="13" viewBox="0 0 48 40" fill="none" aria-hidden="true"><path d="M9 27C11 16.5 17 7.5 26 5c3.4-.9 6 .8 6 4.4V27Z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M4 33.5q4-3.5 8.5 0t8.5 0t8.5 0t8.5 0t6.5 0" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>
    </div>
    <div class="card">
      <!-- 第 1 步 -->
      <template v-if="step === 0">
        <div class="card-hd">第 1 步 · 写剧本<span class="pill p-info">{{ script ? `第 ${script.version || 1} 稿` : '还没生成' }}</span></div>
        <div class="card-bd">
          <template v-if="script?.episodes?.length">
            <p>由你配置的文本模型生成，共 {{ script.episodes.length }} 集，已保存到本机。</p>
            <div class="script" style="margin-top:14px">
              <template v-for="(ep, i) in script.episodes" :key="i">
                <p><b>第 {{ ep.idx || i + 1 }} 集 · {{ ep.title }}</b></p>
                <p>{{ ep.script }}</p>
              </template>
            </div>
            <div class="acts">
              <button class="btn btn-p" @click="project.goto(1)">确认这一稿，看大纲</button>
              <button class="btn btn-s" :disabled="project.contentBusy" @click="doGenScript">{{ project.contentBusy ? '生成中…' : '重新生成这一稿' }}</button>
            </div>
            <div class="note">剧本由你配置的模型生成；没有配置文本模型时不会有任何剧本内容。</div>
          </template>
          <template v-else>
            <p>还没有剧本。用你在设置里配置的文本模型，根据想法生成第一稿。</p>
            <div v-if="project.contentError" class="hint-warn">{{ project.contentError }}</div>
            <div v-if="project.contentBusy" class="gen-busy">
              <span class="busy-dot"></span> 正在调用你配置的文本模型生成剧本…
            </div>
            <div v-if="project.streamText" class="stream-text">{{ project.streamText }}<span class="caret">▍</span></div>
            <div class="acts">
              <button class="btn btn-p" :disabled="project.contentBusy" @click="doGenScript">{{ project.contentBusy ? '正在生成…' : '用我的模型生成剧本' }}</button>
              <button class="btn btn-s" @click="router.push('/settings')">去配置文本模型</button>
            </div>
            <div class="note">没有配置或没测通文本模型时，这里不会显示任何假剧本。</div>
          </template>
        </div>
      </template>
      <!-- 第 2 步 -->
      <template v-else-if="step === 1">
        <div class="card-hd">第 2 步 · 确认剧本<span class="pill p-wait">等你确认</span></div>
        <div class="card-bd">
          <p>看看故事走向对不对。内容是刚生成的真实剧本。</p>
          <div v-if="script?.episodes?.length" style="margin-top:10px">
            <div v-for="(ep, i) in script.episodes" :key="i" class="ep">
              <span class="no">EP.{{ String(ep.idx || i + 1).padStart(2, '0') }}</span>
              <div><h5>{{ ep.title }}</h5><div class="tags"><span v-for="(t, j) in (ep.tags || [])" :key="j" class="tag">{{ t }}</span></div></div>
            </div>
          </div>
          <div v-else class="hint-warn">还没有剧本，请先回到第 1 步生成。</div>
          <div class="acts">
            <button class="btn btn-p" :disabled="!script?.episodes?.length" @click="project.goto(2)">确认剧本，开始定角色</button>
            <button class="btn btn-s" @click="project.goto(0)">回去改剧本</button>
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
                <img v-if="r.ref_url" :src="r.ref_url" :alt="`${r.name}的定妆图`">
                <div v-else class="role-ph">无图</div>
                <span class="chk"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#04121c" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>
                <span class="lab">{{ r.name }}</span>
              </div>
            </div>
            <div class="acts">
              <button class="btn btn-p" @click="confirmRoles">确认这 {{ project.selectedRoles.size }} 个角色</button>
              <button class="btn btn-s" :disabled="project.contentBusy" @click="project.genCharacters(5).then(r => ui.toast(r.ok ? '定妆图已重新生成' : (r.error || '生成失败')))">全部重新生成</button>
            </div>
            <div class="note">真实定妆图由图片模型生成；返回链接type的图片会直接展示。</div>
          </template>
          <template v-else>
            <p>还没有定妆图。用你在设置里配置的图片模型生成角色形象。</p>
            <div v-if="project.contentError" class="hint-warn">{{ project.contentError }}</div>
            <div class="acts">
              <button class="btn btn-p" :disabled="project.contentBusy" @click="project.genCharacters(5).then(r => ui.toast(r.ok ? '定妆图已生成' : (r.error || '生成失败')))">{{ project.contentBusy ? '生成中…' : '用我的模型生成定妆图' }}</button>
              <button class="btn btn-s" @click="router.push('/settings')">去配置图片模型</button>
            </div>
            <div class="note">没有配置图片模型时，这里不会显示任何假角色脸。</div>
          </template>
        </div>
      </template>
      <!-- 第 4 步 -->
      <template v-else-if="step === 3">
        <div class="card-hd">第 4 步 · 确认角色形象<span class="pill" :class="project.locked ? 'p-ok' : 'p-wait'">{{ project.locked ? '已确认' : '等你确认' }}</span></div>
        <div class="card-bd">
          <p>这 {{ project.selectedRoles.size }} 个形象会固定在镜头里。现在是：</p>
          <div class="rolegrid" style="margin-top:10px">
            <div v-for="r in project.characters.filter((c:any) => project.selectedRoles.has(c.id))" :key="r.id" class="role">
              <img v-if="r.ref_url" :src="r.ref_url" :alt="r.name"><div v-else class="role-ph">无图</div>
              <span class="lab">{{ r.name }}{{ project.locked ? ' · 已确认' : '' }}</span>
            </div>
          </div>
          <div v-if="!project.selectedRoles.size" class="hint-warn">还没有选中的角色，请先回第 3 步生成并选择。</div>
          <div class="acts">
            <button class="btn btn-p" :disabled="project.locked || !project.selectedRoles.size" @click="ui.lockOpen = true">{{ project.locked ? '已确认' : '确认形象，开始拆镜头' }}</button>
            <button class="btn btn-s" @click="project.goto(2)">回去调整形象</button>
          </div>
          <div class="note w">确认后想换形象，需要把已经做好的镜头重新生成一遍。建议先确认再继续。</div>
        </div>
      </template>
      <!-- 第 5 步 -->
      <template v-else-if="step === 4">
        <div class="card-hd">第 5 步 · 拆分镜头<span class="pill p-info">{{ shots?.shots?.length || 0 }} 个镜头</span></div>
        <div class="card-bd">
          <template v-if="shots?.shots?.length">
            <p>由你配置的文本模型拆分，共 <b>{{ shots.shots.length }}</b> 个镜头，已保存到本机。</p>
            <table class="table" style="margin-top:12px">
              <thead><tr><th>镜头</th><th>场景</th><th>类型</th></tr></thead>
              <tbody>
                <tr v-for="s in shots.shots.slice(0, 6)" :key="s.idx">
                  <td>{{ s.idx }}</td><td>{{ s.scene }}</td>
                  <td><span class="chip" :class="s.importance === 'key' ? 'c-key' : 'c-wait'">{{ s.importance === 'key' ? '重要' : '过渡' }}</span></td>
                </tr>
              </tbody>
            </table>
            <div class="acts">
              <button class="btn btn-p" @click="startGen">按这个方案生成</button>
              <button class="btn btn-s" :disabled="project.contentBusy" @click="doGenShots">重新拆分</button>
            </div>
            <div class="note">生成前会检查视频模型是否已配置并测通；未配置不会扣钱也不会伪造画面。</div>
          </template>
          <template v-else>
            <p>还没有镜头表。先由文本模型根据剧本拆分镜头。</p>
            <div v-if="project.contentError" class="hint-warn">{{ project.contentError }}</div>
            <div class="acts">
              <button class="btn btn-p" :disabled="project.contentBusy" @click="doGenShots">{{ project.contentBusy ? '拆分中…' : '用我的模型拆分镜头' }}</button>
              <button class="btn btn-s" @click="project.goto(0)">回去写剧本</button>
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
          <div class="progress"><i v-for="n in (gen.total || 12)" :key="n" :class="{ on: n <= done }"></i></div>
          <div style="display:flex;justify-content:space-between;align-items:baseline">
            <span class="big-num">{{ gen.total ? Math.round(done / gen.total * 100) : 0 }}%</span>
            <span style="font-size:11px;color:var(--ink3);font-family:var(--mono)">已完成 {{ done }} 个 · 失败 {{ gen.failed }} 个（不计费）<template v-if="gen.eta"> · 约 {{ gen.eta }} 秒</template></span>
          </div>
          <table class="table" style="margin-top:12px">
            <thead><tr><th>镜头</th><th>场景</th><th>状态</th></tr></thead>
            <tbody>
              <tr v-for="(it, idx) in gen.items" :key="it.shot_id">
                <td>{{ idx + 1 }}</td><td>{{ it.scene_desc }}</td>
                <td style="text-align:right">
                  <span v-if="it.status === 'done'" class="chip c-ok">可用</span>
                  <span v-else-if="it.status === 'running'" class="chip c-run">生成中</span>
                  <span v-else-if="it.status === 'failed'" class="chip c-fail" :title="it.fail_reason || ''">失败</span>
                  <span v-else class="chip c-wait">排队中</span>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="gen.notStarted" class="hint-warn">还没有开始生成。请回第 5 步确认镜头后开始；这里只显示引擎的真实进度，没有演示动画。</div>
          <div class="acts">
            <template v-if="!gen.total">
              <button class="btn btn-p" @click="project.goto(4)">回上一步开始生成</button>
            </template>
            <template v-else-if="done < gen.total">
              <button class="btn btn-p" @click="gen.paused ? gen.resume(project.currentId || '') : gen.pause(project.currentId || ''); ui.toast(gen.paused ? '已继续生成' : '已暂停，进度已保存')">{{ gen.paused ? '继续生成' : '暂停生成' }}</button>
              <span class="chip c-wait">真实生成中 · 引擎按镜头推进</span>
            </template>
            <template v-else>
              <button class="btn btn-p" @click="project.goto(6)">看成片</button>
            </template>
          </div>
          <div class="note">关掉窗口不会丢进度，下次打开从这一格继续。没有"跳过等待"——真实任务无法伪造完成。</div>
        </div>
      </template>
      <!-- 第 7 步 -->
      <template v-else-if="step === 6">
        <div class="card-hd">第 7 步 · 看成片<span class="pill p-info">真实素材</span></div>
        <div class="card-bd">
          <template v-if="firstAsset">
            <p>这是模型真实生成的画面。点开查看，不满意可回对应镜头重新生成。</p>
            <div class="player" style="margin-top:14px">
              <img :src="firstAsset" alt="生成的真实画面">
            </div>
            <div class="acts" style="justify-content:center">
              <button class="btn btn-s" @click="window_open(firstAsset)">在新窗口查看</button>
              <button class="btn btn-p" @click="project.goto(7)">导出整集</button>
            </div>
            <div class="note">画面来自你配置的视频模型；没有真实素材时不会显示任何示例画面。</div>
          </template>
          <template v-else>
            <p>还没有真实画面。需要先在第 6 步完成生成，模型返回素材后这里才会显示。</p>
            <div class="acts" style="justify-content:center">
              <button class="btn btn-p" @click="project.goto(4)">去生成画面</button>
            </div>
            <div class="note">这里不会用示例剧照冒充成片。</div>
          </template>
        </div>
      </template>
      <!-- 第 8 步 -->
      <template v-else>
        <div class="card-hd">第 8 步 · 导出视频<span class="pill" :class="project.exp.state === 'done' ? 'p-ok' : 'p-off'">{{ project.exp.state === 'done' ? '已导出' : project.exp.state === 'running' ? '导出中' : '未开始' }}</span></div>
        <div class="card-bd">
          <p>导出设置好就可以发。默认竖屏，带字幕和 AI 生成标识。</p>
          <div style="margin-top:12px;display:flex;flex-direction:column;gap:7px">
            <div class="ch" :class="{ sel: project.ratio === 'v' }" @click="project.ratio = 'v'"><span class="rad"></span><div><div class="t">竖屏 1080 × 1920</div><div class="d">适合抖音、视频号</div></div><span class="pr">MP4</span></div>
            <div class="ch" :class="{ sel: project.ratio === 'h' }" @click="project.ratio = 'h'"><span class="rad"></span><div><div class="t">横屏 1920 × 1080</div><div class="d">适合 B 站、YouTube</div></div><span class="pr">MP4</span></div>
          </div>
          <div v-if="project.exp.state === 'running'" class="progress solid" style="margin-top:16px"><i :style="{ width: `${project.exp.pct}%` }"></i></div>
          <div class="acts">
            <button v-if="project.exp.state === 'idle'" class="btn btn-p" @click="doExport">开始导出</button>
            <template v-if="project.exp.state === 'done'">
              <button class="btn btn-p" @click="engine.openFolder('works'); ui.toast('已打开作品库文件夹')">下载视频</button>
              <button class="btn btn-s" @click="router.push('/works')">去作品库</button>
              <button class="btn btn-s" @click="doExport">重新导出</button>
            </template>
            <button v-if="project.exp.state === 'running'" class="btn btn-s" disabled>导出中…</button>
            <span style="font-size:11px;color:var(--ink3);font-family:var(--mono)">只导出本机真实生成的素材</span>
          </div>
          <div class="note">已自动加入"AI 生成"标识。没有真实素材时不会导出演示片；发布前仍需按平台要求完成备案。</div>
        </div>
      </template>
    </div>
  </div>
</template>
