<script setup lang="ts">
import { computed } from 'vue'
import { useProjectStore } from '@/stores/project'
import { useGenStore } from '@/stores/gen'
import { useUiStore } from '@/stores/ui'
const project = useProjectStore()
const gen = useGenStore()
const ui = useUiStore()
const tab = computed(() => project.tab)
const done = computed(() => gen.done)
const realCost = computed(() => Math.round(gen.items.reduce((a: number, b: any) => a + (b.cost || 0), 0) * 10) / 10)
const money = (n: number) => `${n.toFixed(1)} 元`
function statusChip(s: string) {
  if (s === 'done') return { cls: 'c-ok', text: '可用' }
  if (s === 'running') return { cls: 'c-run', text: '生成中' }
  if (s === 'failed') return { cls: 'c-fail', text: '失败' }
  return { cls: 'c-wait', text: '排队' }
}
</script>
<template>
  <aside class="right" aria-label="项目内容">
    <div class="rtabs">
      <button :class="{ on: tab === 'shots' }" @click="project.tab = 'shots'">镜头</button>
      <button :class="{ on: tab === 'roles' }" @click="project.tab = 'roles'">角色</button>
      <button :class="{ on: tab === 'cost' }" @click="project.tab = 'cost'">花费</button>
    </div>
    <div class="rbody">
      <template v-if="tab === 'shots'">
        <div v-if="!gen.items.length" class="empty-mini">还没有生成镜头，开始生成后这里显示引擎的真实状态。</div>
        <div v-for="(it, i) in gen.items" :key="it.shot_id" class="row">
          <div class="row-ph">{{ i + 1 }}</div>
          <div class="m"><div class="t">{{ i + 1 }}. {{ it.scene_desc }}</div><div class="s">{{ it.fail_reason || '真实生成任务' }}</div></div>
          <span class="chip" :class="statusChip(it.status).cls">{{ statusChip(it.status).text }}</span>
        </div>
      </template>
      <template v-else-if="tab === 'roles'">
        <div v-if="!project.characters.length" class="empty-mini">还没有定妆图，去第 3 步用图片模型生成。</div>
        <div v-for="r in project.characters" :key="r.id" class="row">
          <img v-if="r.ref_url" :src="r.ref_url" alt="">
          <div v-else class="row-ph">照</div>
          <div class="m"><div class="t">{{ r.name }}</div><div class="s">{{ project.locked ? '已确认' : (project.selectedRoles.has(r.id) ? '已选中' : '未选中') }}</div></div>
          <span class="chip" :class="project.locked ? 'c-ok' : 'c-wait'">{{ project.locked ? '已确认' : '待确认' }}</span>
        </div>
      </template>
      <template v-else>
        <div class="metric"><div class="l">已生成镜头</div><div class="v">{{ done }}</div></div>
        <div class="metric"><div class="l">失败（不计费）</div><div class="v">{{ gen.failed }}</div></div>
        <div class="metric"><div class="l">已发生费用（引擎记账）</div><div class="v">{{ money(realCost) }}</div></div>
        <div class="metric" style="border-bottom:none"><div class="l">失败花费</div><div class="v">0.0 元</div></div>
        <div class="note">费用来自引擎的真实账单事件；自带密钥生成的成本按公开单价估算，不扣平台额度。</div>
        <button class="btn btn-t" @click="ui.toast('额度与账单以本机账本为准')">查看账本说明</button>
      </template>
    </div>
  </aside>
</template>
