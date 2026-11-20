<script setup lang="ts">
import { STEPS } from '@/constants'
import { useProjectStore } from '@/stores/project'
const project = useProjectStore()
</script>
<template>
  <aside class="side" aria-label="制作步骤">
    <div class="side-t">制作步骤 / 08</div>
    <div v-for="(s, i) in STEPS" :key="s.n"
      class="st" :class="i < project.step ? 'done' : i === project.step ? 'now' : 'todo'"
      @click="project.goto(i)" role="button" tabindex="0">
      <div class="mk">
        <svg v-if="i < project.step" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
        <span v-else>{{ String(i + 1).padStart(2, '0') }}</span>
      </div>
      <div><div class="nm">{{ s.n }}</div><div class="ds">{{ s.d }}</div></div>
    </div>
    <div class="side-foot">
      <div class="l">一次生成能直接用的比例</div><div class="v">78%</div>
      <div class="bar"><i style="width:78%"></i></div><div class="sm">同类作品平均 40%</div>
    </div>
  </aside>
</template>
