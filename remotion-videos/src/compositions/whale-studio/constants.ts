// ============ EDITABLE CONSTANTS ============
// 品牌、排版、文案、时序——改视频只需改这里，不用动组件内部。
export const BRAND = {
  bg: '#0d1420',
  surface: '#181722',
  surface2: '#201E2D',
  accent: '#00d4ff',
  accentDim: 'rgba(0,212,255,0.14)',
  text: '#e7f0f9',
  text2: '#9cafc5',
  ok: '#2fe08a',
  danger: '#ff5c6c',
  gold: '#e8b96a',
  font: '"Noto Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif',
  mono: '"JetBrains Mono", "Cascadia Mono", Consolas, monospace',
};
export const TYPO = {
  hero: 74,
  h1: 62,
  h2: 44,
  body: 30,
  small: 24,
  caption: 20,
  weight: 700 as const,
};
// 场景帧长（合计 1800 = 60s @ 30fps）
export const TIMING = {
  fps: 30,
  scenes: [150, 180, 180, 300, 210, 210, 180, 210, 180] as const,
  fade: 18,
  stagger: 16,
};
export const STEPS = [
  '写剧本', '确认剧本', '定角色', '锁形象',
  '拆镜头', '生成画面', '看成片', '导出视频',
] as const;
export const MODE_CARDS = [
  { t: '平台额度', d: '零配置起步' },
  { t: '自带密钥', d: '更省钱' },
  { t: '本地模型', d: '完全离线' },
] as const;
export const PAINS = [
  '角色每集换脸，前后不连贯',
  '算力烧了，钱花在哪不知道',
  '一套流程在五个工具间反复搬运',
] as const;
export const VALUES = [
  { num: 3, unit: '集', sub: '从想法到成片' },
  { num: 8, unit: '步', sub: '全程对话陪跑' },
  { num: 0, unit: '', sub: '数据上云' },
] as const;
// 每场景的起始帧（由 scenes 累加得到，组件里用 from 相对帧）
export const SCENE_STARTS: number[] = (() => {
  const acc: number[] = [];
  let t = 0;
  for (const d of TIMING.scenes) { acc.push(t); t += d; }
  return acc;
})();
export const TOTAL_FRAMES = TIMING.scenes.reduce((a, b) => a + b, 0);
// ============================================
