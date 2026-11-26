<script setup lang="ts">
/** 模型调用日志面板：把每次真实调用摊开给用户看，不再是黑盒。 */
import { computed, ref } from 'vue'
import { useCallsStore } from '@/stores/calls'

const props = withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
const calls = useCallsStore()
const open = ref(true)

const rows = computed(() => calls.live)

function statusText(e: any) {
  if (!e.status) return '失败'
  return String(e.status)
}
function isFail(e: any) { return !e.status || e.status >= 400 }
</script>

<template>
  <div class="calllog" :class="{ compact: props.compact }">
    <button class="cl-head" type="button" @click="open = !open" :aria-expanded="open">
      <span class="cl-t">模型调用日志</span>
      <span class="cl-n">{{ rows.length }} 次调用</span>
      <span class="cl-arrow">{{ open ? '▾' : '▸' }}</span>
    </button>
    <div v-if="open" class="cl-body">
      <div v-if="!rows.length" class="cl-empty">本次生成还没有发出任何请求。</div>
      <div v-for="(e, i) in rows" :key="i" class="cl-row" :class="{ fail: isFail(e) }">
        <span class="cl-ts">{{ e.ts }}</span>
        <span class="cl-code">{{ statusText(e) }}</span>
        <span class="cl-ms">{{ e.ms }}ms</span>
        <span class="cl-desc">{{ e.error || e.note || (e.method + ' ' + e.path) }}</span>
        <span v-if="e.attempt > 1" class="cl-retry">第{{ e.attempt }}次</span>
      </div>
      <div v-if="rows.length" class="cl-foot">
        {{ rows[0].model }} · {{ rows[0].endpoint }}{{ rows[0].path }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.calllog{margin-top:12px;border:1px solid var(--line);border-radius:6px;overflow:hidden;background:var(--panel2)}
.cl-head{width:100%;display:flex;align-items:center;gap:8px;padding:8px 11px;background:none;border:none;color:var(--ink2);font-size:11.5px;cursor:pointer;text-align:left}
.cl-head:hover{color:var(--ink)}
.cl-t{font-weight:600;color:var(--ink)}
.cl-n{color:var(--ink3);font-family:var(--mono);font-size:10.5px}
.cl-arrow{margin-left:auto;color:var(--ink3)}
.cl-body{padding:0 11px 9px}
.cl-empty{font-size:11px;color:var(--ink3);padding:2px 0 6px}
.cl-row{display:flex;align-items:baseline;gap:8px;font-family:var(--mono);font-size:10.5px;line-height:1.9;color:var(--ink2);border-top:1px solid var(--line)}
.cl-ts{color:var(--ink3);flex-shrink:0}
.cl-code{flex-shrink:0;min-width:30px;color:var(--ok)}
.cl-row.fail .cl-code{color:var(--danger,#ff5c6c)}
.cl-ms{flex-shrink:0;color:var(--ink3);min-width:48px}
.cl-desc{flex:1;color:var(--ink2);word-break:break-all}
.cl-row.fail .cl-desc{color:var(--warn,#ffb547)}
.cl-retry{flex-shrink:0;color:var(--warn,#ffb547)}
.cl-foot{margin-top:6px;font-size:10px;color:var(--ink3);font-family:var(--mono);word-break:break-all}
</style>
