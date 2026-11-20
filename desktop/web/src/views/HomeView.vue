<script setup lang="ts">
import IdeaBox from '@/components/home/IdeaBox.vue'
import ProjectList from '@/components/home/ProjectList.vue'
</script>
<template>
  <main class="view on">
    <div class="home">
      <div class="home-hero">
        <h1>今天，想做一部什么剧？</h1>
        <p>一句话描述你的想法，助手带你从剧本走到成片。你只需要在三件事上确认：剧本、角色、前 30 秒。</p>
      </div>
      <IdeaBox />
      <ProjectList />
      <p class="home-note">密钥和素材只存在你的电脑上，调用直接发给模型厂商。没有模型也能先用平台额度试做第一集。</p>
    </div>
  </main>
</template>
