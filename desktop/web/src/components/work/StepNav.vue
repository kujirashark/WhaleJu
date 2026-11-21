<script setup lang="ts">
import { computed } from 'vue'
import { STEPS } from '@/constants'
import { useProjectStore } from '@/stores/project'
const project = useProjectStore()
/**
 * 步骤描述必须来自真实项目状态。
 * 以前这里是写死的文案（"前 30 秒"、"12 个镜头"），
 * 实际项目可能是 50 秒、24 个镜头 —— 界面对用户说假话。
 */
const stepDesc = computed<Record<number, string>>(() => {
  const eps = project.script?.episodes?.length || 0
  const shots = project.shots?.shots?.length || 0
  const chars = project.characters.length
  // 第 6 步生成的每张画面在成片里占 2 秒（引擎的合成参数）
  const frames = project.assets.filter((a: any) => a.kind === 'shot').length
  const seconds = frames * 2
  return {
    0: eps ? `${eps} 集` : '还没写',
    1: eps ? '你确认后才继续' : '等第 1 步',
    2: chars ? `${chars} 个角色` : '还没定妆',
    3: chars ? '必须你确认' : '等第 3 步',
    4: shots ? `${shots} 个镜头` : '还没拆',
    5: frames ? `${frames} 张画面` : '失败不计费',
    6: seconds ? `${seconds} 秒成片` : '还没生成',
    7: '导出成片',
  }
})
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
      <div><div class="nm">{{ s.n }}</div><div class="ds">{{ stepDesc[i] || s.d }}</div></div>
    </div>
  </aside>
</template>
