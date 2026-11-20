<script setup lang="ts">
import StepNav from '@/components/work/StepNav.vue'
import StepBody from '@/components/work/StepBody.vue'
import RightPanel from '@/components/work/RightPanel.vue'
import ChatStream from '@/components/work/ChatStream.vue'
</script>
<template>
  <main class="view on">
    <div class="bench">
      <StepNav />
      <section class="main" aria-label="工作区">
        <div class="stream"><StepBody /></div>
        <ChatStream />
      </section>
      <RightPanel />
    </div>
  </main>
</template>
