<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useProjectStore } from '@/stores/project'
import { useGenStore } from '@/stores/gen'
import { useUiStore } from '@/stores/ui'
import { useCallsStore } from '@/stores/calls'
const project = useProjectStore()
const gen = useGenStore()
const ui = useUiStore()
const calls = useCallsStore()
const tab = computed(() => project.tab)
const done = computed(() => gen.done)
/** 镜头清单：与第 6/7 步同源（引擎持久化素材），引擎重启后依然显示真实画面 */
const shotList = computed<any[]>(() => {
  const live = gen.visibleItems() as any[]
  return live.length ? live : ((gen.persisted || []) as any[])
})
function statusChip(s: string) {
  if (s === 'done') return { cls: 'c-ok', text: '可用' }
  if (s === 'running') return { cls: 'c-run', text: '生成中' }
  if (s === 'failed') return { cls: 'c-fail', text: '失败' }
  return { cls: 'c-wait', text: '排队' }
}
// 日志 tab：拉取引擎侧最近记录（覆盖图片/视频/镜头等所有能力）
watch(tab, (t) => { if (t === 'calls') calls.load(80) })
onMounted(() => { if (tab.value === 'calls') calls.load(80) })
</script>
<template>
  <aside class="right" aria-label="项目内容">
    <div class="rtabs">
      <button :class="{ on: tab === 'shots' }" @click="project.tab = 'shots'">镜头</button>
      <button :class="{ on: tab === 'roles' }" @click="project.tab = 'roles'">角色</button>
      <button :class="{ on: tab === 'cost' }" @click="project.tab = 'cost'">用量</button>
      <button :class="{ on: tab === 'calls' }" @click="project.tab = 'calls'">日志</button>
    </div>
    <div class="rbody">
      <template v-if="tab === 'shots'">
        <div v-if="!shotList.length" class="empty-mini">还没有生成镜头，开始生成后这里显示引擎的真实状态。</div>
        <div v-for="(it, i) in shotList" :key="it.shot_id" class="row">
          <!-- 缩略图：右侧也要看得见真实画面，不能只有一行字 -->
          <img v-if="it.media_url && it.kind !== 'video'" class="row-thumb" :src="project.assetUrl(it.media_url)" alt="" loading="lazy">
          <div v-else-if="it.media_url" class="row-thumb video-thumb"><span>▶</span></div>
          <div v-else class="row-ph">{{ i + 1 }}</div>
          <div class="m"><div class="t">{{ i + 1 }}. {{ it.scene_desc || `第 ${i + 1} 镜` }}</div><div class="s">{{ it.fail_reason || '真实生成任务' }}</div></div>
          <span class="chip" :class="statusChip(it.status).cls">{{ statusChip(it.status).text }}</span>
        </div>
      </template>
      <template v-else-if="tab === 'roles'">
        <div v-if="!project.characters.length" class="empty-mini">还没有定妆图，去第 3 步用图片模型生成。</div>
        <div v-for="r in project.characters" :key="r.id" class="row">
          <img v-if="project.assetUrl(r.ref_url) || project.assetUrl(r.remote_url)" :src="project.assetUrl(r.ref_url) || project.assetUrl(r.remote_url)" alt="" loading="lazy">
          <div v-else class="row-ph">照</div>
          <!-- 状态一律读引擎事实（characters.locked）：以前这里读前端内存态，
               刷新就丢，同一屏会出现"中间已确认 / 右侧待确认"两套说法 -->
          <div class="m">
            <div class="t">{{ r.name }}</div>
            <div class="s">{{ project.rolesLocked ? '形象已锁定' : (project.selectedRoles.has(r.id) ? '已选中，待确认' : '未选中') }}</div>
          </div>
          <span class="chip" :class="project.rolesLocked ? 'c-ok' : 'c-wait'">{{ project.rolesLocked ? '已确认' : '待确认' }}</span>
        </div>
      </template>
      <template v-else-if="tab === 'calls'">
        <div v-if="!calls.items.length" class="empty-mini">还没有模型调用记录。发起一次生成后，这里会列出真实的请求、状态码与耗时。</div>
        <div v-for="(e, i) in calls.items" :key="i" class="row call-row">
          <div class="m">
            <div class="t">{{ e.method }} {{ e.path || '/' }} · {{ e.status || '失败' }}</div>
            <div class="s">{{ e.ts }} · {{ e.ms }}ms · {{ e.model }}<template v-if="e.attempt > 1"> · 第{{ e.attempt }}次</template></div>
            <div v-if="e.error || e.note" class="s" :class="{ bad: !!e.error }">{{ e.error || e.note }}</div>
          </div>
        </div>
        <button class="btn btn-t" @click="calls.load(80)">刷新</button>
      </template>
      <template v-else>
        <div class="metric"><div class="l">已生成镜头</div><div class="v">{{ done }}</div></div>
        <div class="metric"><div class="l">失败镜头</div><div class="v">{{ gen.failed }}</div></div>
        <div class="metric" style="border-bottom:none"><div class="l">总镜头数</div><div class="v">{{ gen.total || done }}</div></div>
        <div class="note">用量数据来自引擎的真实任务事件，保存在本机。生成消耗的是你自己的厂商额度，本软件免费开源、不做任何收费。</div>
      </template>
    </div>
  </aside>
</template>
