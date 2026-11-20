<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { TEMPLATES } from '@/constants'
import { useProjectStore } from '@/stores/project'
import { useUiStore } from '@/stores/ui'
const router = useRouter()
const project = useProjectStore()
const ui = useUiStore()
const idea = ref('')
function fill(tpl: string) {
  idea.value = TEMPLATES[tpl] || ''
}
async function create() {
  const v = idea.value.trim()
  if (!v) {
    ui.toast('先写一句你的想法，或者点下面的题材模板')
    return
  }
  ui.toast('正在写入本机项目库…')
  const ok = await project.create(v)
  if (ok) {
    project.goto(0)
    router.push('/p/current')
    ui.toast('项目已保存到本机，开始写第一稿')
  } else {
    ui.toast('未连接引擎，当前为演示模式；界面可继续体验流程')
    project.goto(0)
    router.push('/p/current')
  }
}
defineExpose({ idea })
</script>
<template>
  <div class="home-box">
    <textarea v-model="idea" rows="2" placeholder="例如：讲一个普通人的一生，从八岁到七十岁，三集竖屏短剧" aria-label="描述你想做的剧"></textarea>
    <div class="home-box-ft">
      <div class="chips">
        <button class="chip" :class="{ 'c-run': idea === TEMPLATES.life }" @click="fill('life')">普通人的一生</button>
        <button class="chip" @click="fill('city')">都市逆袭</button>
        <button class="chip" @click="fill('mystery')">悬疑反转</button>
      </div>
      <button class="btn btn-p" @click="create">开始创作</button>
    </div>
  </div>
</template>
