<script setup lang="ts">
import { computed } from 'vue'
import { ROLES, SHOTS } from '@/constants'
import { useProjectStore } from '@/stores/project'
import { useGenStore } from '@/stores/gen'
const project = useProjectStore()
const gen = useGenStore()
const tab = computed(() => project.tab)
const done = computed(() => gen.done)
const used = computed(() => SHOTS.slice(0, done.value).reduce((a, b) => a + b.cost, 0))
const fee = computed(() => Math.round(used.value * 0.15 * 10) / 10)
const money = (n: number) => `${n} 元`
function shotChip(i: number) {
  if (i <= done.value) return { cls: 'c-ok', text: '可用' }
  if (!gen.paused && i === done.value + 1) return { cls: 'c-run', text: '生成中' }
  if (i === 5) return { cls: 'c-fail', text: '失败' }
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
        <div v-for="s in SHOTS" :key="s.i" class="row">
          <img :src="s.img" alt="">
          <div class="m"><div class="t">{{ s.i }}. {{ s.t }}</div><div class="s">{{ s.model }}</div></div>
          <span class="chip" :class="shotChip(s.i).cls">{{ shotChip(s.i).text }}</span>
        </div>
      </template>
      <template v-else-if="tab === 'roles'">
        <div v-for="r in ROLES" :key="r.k" class="row">
          <img :src="r.img" alt="">
          <div class="m"><div class="t">{{ r.name }}</div><div class="s">{{ project.locked ? '已确认 · 用于 12 个镜头' : '待确认' }}</div></div>
          <span class="chip" :class="project.locked ? 'c-ok' : 'c-wait'">{{ project.locked ? '已确认' : '待确认' }}</span>
        </div>
      </template>
      <template v-else>
        <div class="metric"><div class="l">已生成 {{ done }} 个镜头</div><div class="v">{{ money(used) }}</div></div>
        <div class="metric"><div class="l">其中平台手续费 15%</div><div class="v">{{ money(fee) }}</div></div>
        <div class="metric"><div class="l">失败与废弃</div><div class="v">0 元</div></div>
        <div class="metric" style="border-bottom:none"><div class="l">整集预计（12 个）</div><div class="v">173 元</div></div>
        <div class="mini-bars" aria-hidden="true"><i v-for="v in [38,52,44,68,55,74,61,82,70,88,76,94]" :key="v" :style="{ height: `${v}%` }"></i></div>
        <div class="note">全部换成你自己的密钥，可少付约 11 元手续费。</div>
      </template>
    </div>
  </aside>
</template>
