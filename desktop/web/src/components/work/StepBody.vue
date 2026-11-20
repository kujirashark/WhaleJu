<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { IMG, ROLES, SHOTS } from '@/constants'
import { useProjectStore } from '@/stores/project'
import { useUiStore } from '@/stores/ui'
import { engine } from '@/api/engine'
const router = useRouter()
const project = useProjectStore()
const ui = useUiStore()
const step = computed(() => project.step)
const done = computed(() => project.gen.done)
function confirmRoles() {
  if (!project.selectedRoles.size) { ui.toast('至少选一个角色'); return }
  project.goto(3)
  ui.toast(`已选 ${project.selectedRoles.size} 个角色`)
}
async function startGen() {
  await project.submitGen('人的一生 · 黄昏院子里的孩子')
  project.goto(5)
  project.startGen()
  ui.toast(project.routeReason ? `已提交本机引擎：${project.routeReason}` : '开始生成，失败的会自动换一家重试')
}
async function doExport() {
  project.startExport()
  const work = await project.exportWork()
  if (work?.demo) ui.toast('演示成片已存入作品库（视频槽还是模拟，尚未生成真实画面）')
  else if (work) ui.toast('成片已存入本机作品库（AI 标识已自动写入）')
}
const money = (n: number) => `${n} 元`
</script>
<template>
  <div class="who">
    <div class="av">
      <svg width="16" height="13" viewBox="0 0 48 40" fill="none" aria-hidden="true"><path d="M9 27C11 16.5 17 7.5 26 5c3.4-.9 6 .8 6 4.4V27Z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M4 33.5q4-3.5 8.5 0t8.5 0t8.5 0t8.5 0t6.5 0" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>
    </div>
    <div class="card">
      <!-- 第 1 步 -->
      <template v-if="step === 0">
        <div class="card-hd">第 1 步 · 写剧本<span class="pill p-info">第 {{ project.scriptVer }} 稿</span></div>
        <div class="card-bd">
          <p>按你说的"普通人的一生"，写了三集。每集一个年龄，一共标了 8 个情绪高点。</p>
          <div class="script" style="margin-top:14px">
            <p><b>第 1 集 · 院子里的下午</b></p>
            <p>八岁那年夏天，<span class="hl">他从晾衣绳下跑过</span>，母亲的衬衫在风里鼓起来。他不肯回家吃饭，因为<span class="hl">蝉还在叫</span>。傍晚父亲推着自行车进门，车筐里有一块西瓜。</p>
          </div>
          <div class="acts">
            <button class="btn btn-p" @click="project.goto(1); ui.toast('第 1 稿已确认，再看一眼三集大纲')">确认这一稿，去定角色</button>
            <button class="btn btn-s" @click="project.scriptVer++; ui.toast(`已重写第 ${project.scriptVer} 稿，剧本不产生视频费用`)">重新生成这一稿</button>
            <button class="btn btn-t" @click="ui.toast('在下面输入框告诉它哪里不对')">告诉它哪里不对</button>
          </div>
          <div class="note">剧本由你选的模型生成；定稿之前不会产生视频费用。</div>
        </div>
      </template>
      <!-- 第 2 步 -->
      <template v-else-if="step === 1">
        <div class="card-hd">第 2 步 · 确认剧本<span class="pill p-wait">等你确认</span></div>
        <div class="card-bd">
          <p>三集，五个年龄。看看故事走向对不对。</p>
          <div style="margin-top:10px">
            <div class="ep"><span class="no">EP.01</span><div><h5>院子里的下午 · 八岁</h5><div class="tags"><span class="tag">夏天</span><span class="tag">西瓜</span><span class="tag">蝉声</span></div></div></div>
            <div class="ep"><span class="no">EP.02</span><div><h5>站台 · 十八岁</h5><div class="tags"><span class="tag">离乡</span><span class="tag">绿皮车</span></div></div></div>
            <div class="ep"><span class="no">EP.03</span><div><h5>长椅 · 七十岁</h5><div class="tags"><span class="tag">黄昏</span><span class="tag">回望</span></div></div></div>
          </div>
          <div class="acts">
            <button class="btn btn-p" @click="project.goto(2); ui.toast('剧本已确认，下一步定角色')">确认剧本，开始定角色</button>
            <button class="btn btn-s" @click="project.goto(0)">回去改剧本</button>
          </div>
        </div>
      </template>
      <!-- 第 3 步 -->
      <template v-else-if="step === 2">
        <div class="card-hd">第 3 步 · 角色形象<span class="pill p-info">5 个年龄</span></div>
        <div class="card-bd">
          <p>同一个人，五个年龄。点图片选或取消，选中的会用在全部镜头里。</p>
          <div class="rolegrid">
            <div v-for="r in ROLES" :key="r.k" class="role" :class="{ sel: project.selectedRoles.has(r.k) }" @click="project.toggleRole(r.k)">
              <img :src="r.img" :alt="`${r.name}的角色形象`">
              <span class="sw" @click.stop="ui.toast(`已为「${r.name}」换了一张参考图（不额外收费）`)">换一张</span>
              <span class="chk"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#04121c" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>
              <span class="lab">{{ r.name }}</span>
            </div>
          </div>
          <div class="acts">
            <button class="btn btn-p" @click="confirmRoles">确认这 {{ project.selectedRoles.size }} 个角色</button>
            <button class="btn btn-s" @click="ui.toast('已重新生成 5 组参考图，本次不额外收费')">全部重新生成</button>
            <span style="font-size:11px;color:var(--ink3);font-family:var(--mono)">重新生成不额外收费</span>
          </div>
          <div class="note">每个年龄都能单独换。换完之后，用它做过的镜头需要重做。</div>
        </div>
      </template>
      <!-- 第 4 步 -->
      <template v-else-if="step === 3">
        <div class="card-hd">第 4 步 · 确认角色形象<span class="pill" :class="project.locked ? 'p-ok' : 'p-wait'">{{ project.locked ? '已确认' : '等你确认' }}</span></div>
        <div class="card-bd">
          <p>这 5 个形象会固定在 <b>12 个镜头</b>里。现在是：</p>
          <div class="rolegrid" style="margin-top:10px">
            <div v-for="r in ROLES" :key="r.k" class="role"><img :src="r.img" :alt="r.name"><span class="lab">{{ r.name }}{{ project.locked ? ' · 已确认' : '' }}</span></div>
          </div>
          <div class="acts">
            <button class="btn btn-p" :disabled="project.locked" @click="ui.lockOpen = true">{{ project.locked ? '已确认' : '确认形象，开始拆镜头' }}</button>
            <button class="btn btn-s" @click="project.goto(2)">回去调整形象</button>
          </div>
          <div class="note w">确认后想换形象，需要把已经做好的镜头重新生成一遍。建议先确认再继续。</div>
        </div>
      </template>
      <!-- 第 5 步 -->
      <template v-else-if="step === 4">
        <div class="card-hd">第 5 步 · 拆分镜头<span class="pill p-info">12 个镜头</span></div>
        <div class="card-bd">
          <p>拆成 12 个镜头：<b>6 个重要镜头</b>、<b>6 个过渡镜头</b>。按这个方案预计 <b>173 元</b>。</p>
          <table class="table" style="margin-top:12px">
            <thead><tr><th class="th2"></th><th>镜头</th><th>类型</th><th>用什么生成</th><th style="text-align:right">预计</th></tr></thead>
            <tbody>
              <tr v-for="s in SHOTS.slice(0, 6)" :key="s.i">
                <td><img :src="s.img" alt=""></td><td>{{ s.i }}. {{ s.t }}</td>
                <td><span class="chip" :class="s.key ? 'c-key' : 'c-wait'">{{ s.key ? '重要' : '过渡' }}</span></td>
                <td>{{ s.model }}</td><td class="num">{{ s.cost }}</td>
              </tr>
            </tbody>
          </table>
          <div class="acts">
            <button class="btn btn-p" @click="startGen">按这个方案生成</button>
            <button class="btn btn-s" @click="project.tab = 'shots'">看全部 12 个</button>
          </div>
          <div class="note">失败重试不收费。可灵余额不够时会先告诉你，不会先扣钱。</div>
        </div>
      </template>
      <!-- 第 6 步 -->
      <template v-else-if="step === 5">
        <div class="card-hd">第 6 步 · 生成画面<span class="pill" :class="done === 12 ? 'p-ok' : 'p-info'">{{ done }} / 12</span></div>
        <div class="card-bd">
          <p>{{ done === 12 ? '12 个镜头都好了。可以先看前 30 秒。' : '正在按镜头逐个生成。失败会自动换一家再试。' }}</p>
          <div class="progress"><i v-for="n in 12" :key="n" :class="{ on: n <= done }"></i></div>
          <div style="display:flex;justify-content:space-between;align-items:baseline">
            <span class="big-num">{{ Math.round(done / 12 * 100) }}%</span>
            <span style="font-size:11px;color:var(--ink3);font-family:var(--mono)">已完成 {{ done }} 个 · 失败 {{ done < 5 ? 1 : 0 }} 个（不计费）</span>
          </div>
          <table class="table" style="margin-top:12px">
            <tbody>
              <tr v-for="s in SHOTS" :key="s.i">
                <td><img :src="s.img" alt=""></td><td>{{ s.i }}. {{ s.t }}</td><td>{{ s.model }}</td>
                <td style="text-align:right">
                  <span v-if="s.i <= done" class="chip c-ok">可用</span>
                  <span v-else-if="project.gen.running && s.i === done + 1" class="chip c-run">生成中</span>
                  <template v-else-if="s.i === 5 && done < 5"><span class="chip c-fail">失败</span> <button class="btn btn-t" @click="ui.toast('已重新排队，失败的任务不收费')">重试</button></template>
                  <span v-else class="chip c-wait">排队中</span>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="acts">
            <template v-if="done < 12">
              <button class="btn btn-p" @click="project.toggleGen()">{{ project.gen.running ? '暂停生成' : '继续生成' }}</button>
              <button class="btn btn-s" @click="project.finishGen(); ui.toast('12 个镜头全部完成')">跳过等待，直接完成</button>
            </template>
            <template v-else>
              <button class="btn btn-p" @click="project.goto(6)">看前 30 秒</button>
              <button class="btn btn-s" @click="project.goto(6); ui.toast('整集重播')">整集重播</button>
            </template>
          </div>
          <div class="note">关掉窗口不会丢进度，下次打开从这一格继续。</div>
        </div>
      </template>
      <!-- 第 7 步 -->
      <template v-else-if="step === 6">
        <div class="card-hd">第 7 步 · 看成片<span class="pill p-info">前 30 秒</span></div>
        <div class="card-bd">
          <p>先看开头 30 秒。不满意只重做这一段。</p>
          <div class="player" style="margin-top:14px">
            <img :src="IMG.child" alt="成片画面：八岁男孩在院子里">
            <div class="ov"><button class="playbtn" @click="project.togglePlay()" aria-label="播放"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg></button></div>
            <div class="pbar"><i :style="{ width: `${project.player.pos / 30 * 100}%` }"></i></div>
            <div class="ptime"><span>00:{{ String(Math.floor(project.player.pos)).padStart(2, '0') }}</span><span>00:30</span></div>
          </div>
          <div class="acts" style="justify-content:center">
            <button class="btn btn-p" @click="project.togglePlay()">{{ project.player.playing ? '暂停' : '播放' }}</button>
            <button class="btn btn-s" @click="ui.toast('正在只重做这一段，其他镜头不动')">重新生成这一段</button>
            <button class="btn btn-s" @click="project.goto(7)">导出整集</button>
          </div>
          <div class="note">重做只影响这一段，其他镜头不动，也不重复收费。</div>
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
            <span style="font-size:11px;color:var(--ink3);font-family:var(--mono)">3 集 · 约 2 分 10 秒 · 约 46 MB</span>
          </div>
          <div class="note">已自动加入"AI 生成"标识。发布前仍需按平台要求完成备案。</div>
        </div>
      </template>
    </div>
  </div>
</template>
