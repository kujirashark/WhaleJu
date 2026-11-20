<script setup lang="ts">
import { useRouter } from 'vue-router'
import { IMG } from '@/constants'
import { useUiStore } from '@/stores/ui'
const router = useRouter()
const ui = useUiStore()
function openWork() {
  router.push('/p/current')
  ui.toast('已打开「人的一生」，从上次的地方继续')
}
</script>
<template>
  <div class="home-recent">
    <div class="home-sec">我的项目 · 2</div>
    <div class="proj" @click="openWork" role="button" tabindex="0" aria-label="打开项目：人的一生">
      <img :src="IMG.hero" alt="项目《人的一生》的示例剧照">
      <div class="pi">
        <div class="t">人的一生 · 3 集</div>
        <div class="s">上次做到：第 4 步 · 确认角色形象</div>
        <div class="pbar2"><i style="width:50%"></i></div>
      </div>
      <span class="chip c-run">4 / 8 步</span>
    </div>
    <div class="proj" @click="router.push('/works')" role="button" tabindex="0" aria-label="打开作品库：都市逆袭">
      <img :src="IMG.teen" alt="项目《都市逆袭》的成片封面">
      <div class="pi">
        <div class="t">都市逆袭 · 3 集</div>
        <div class="s">已完成 · 成片已导出到作品库</div>
        <div class="pbar2"><i style="width:100%"></i></div>
      </div>
      <span class="chip p-ok">已完成</span>
    </div>
  </div>
</template>
