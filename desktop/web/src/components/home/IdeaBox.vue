<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { TEMPLATES } from '@/constants'
import { useProjectStore } from '@/stores/project'
import { useUiStore } from '@/stores/ui'
import { engine } from '@/api/engine'
const router = useRouter()
const project = useProjectStore()
const ui = useUiStore()
const idea = ref('')
/** 提交中：防止连点造成重复建项目 */
const busy = ref(false)
function fill(tpl: string) {
  idea.value = TEMPLATES[tpl] || ''
}
async function create() {
  const v = idea.value.trim()
  if (!v) {
    ui.toast('先写一句你的想法，或者点下面的题材模板')
    return
  }
  // 后端要求至少 2 个字，这里先拦一道，避免白跑一次请求
  if ([...v].length < 2) {
    ui.toast('再多写两个字，至少 2 个字')
    return
  }
  if (busy.value) return
  busy.value = true
  try {
    const ok = await project.create(v)
    if (ok) {
      project.goto(0)
      // 跳真实项目 ID：/p/current 是占位路由，会让 WorkbenchView 拿不到 currentId
      router.push(`/p/${project.currentId}`)
      const n = project.createdEpisodeCount || 1
      ui.toast(n > 1
        ? `项目已保存到本机，按你说的 ${n} 集开工（一集一集写，省额度）`
        : '项目已保存到本机，开始写第一稿')
    } else {
      // 说清真实原因，并提示"可能已经建出来了" ——
      // 引擎在写库后被重启时会出现"实际成功、界面报失败"。
      const why = engine.error || '引擎没有响应'
      ui.toast(`未能创建项目：${why}。可刷新页面确认是否已经建出来。`, 7000)
    }
  } finally {
    busy.value = false
  }
}
defineExpose({ idea })
</script>
<template>
  <div class="home-box">
    <textarea v-model="idea" rows="2" placeholder="例如：深夜便利店连续出现同一张脸，悬疑反转（不说集数就按一集做）" aria-label="描述你想做的剧"></textarea>
    <div class="home-box-ft">
      <div class="chips">
        <button class="chip" :class="{ 'c-run': idea === TEMPLATES.life }" @click="fill('life')">普通人的一生</button>
        <button class="chip" @click="fill('city')">都市逆袭</button>
        <button class="chip" @click="fill('mystery')">悬疑反转</button>
      </div>
      <button class="btn btn-p" :disabled="busy" @click="create">
        {{ busy ? '正在创建…' : '开始创作' }}
      </button>
    </div>
  </div>
</template>
