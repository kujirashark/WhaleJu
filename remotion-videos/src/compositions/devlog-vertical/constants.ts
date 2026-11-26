// ============ EDITABLE CONSTANTS ============
// 鲸鲨漫剧 · 开发进度竖屏视频（抖音）
// 改文案/配色/时长只改这里，不用动组件内部。
export const BRAND = {
  bg: '#0d1420',
  surface: '#181722',
  surface2: '#201e2d',
  accent: '#00d4ff',
  accentDim: 'rgba(0,212,255,0.14)',
  text: '#e7f0f9',
  text2: '#9cafc5',
  ok: '#2fe08a',
  warn: '#e8b96a',
  danger: '#ff5c6c',
  font: '"Noto Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif',
  mono: '"JetBrains Mono", "Cascadia Mono", Consolas, monospace',
};
// 竖屏安全区：左右 60，顶部 80（避开状态栏），底部 160（避开抖音交互区）
export const SAFE = { side: 60, top: 80, bottom: 160 };
export const TYPO = {
  hero: 76,      // 主标题
  h1: 58,        // 场景标题
  h2: 40,        // 副标题
  body: 30,      // 正文
  small: 24,     // 次要说明
  caption: 20,   // 合规声明等细字
  weight: 700 as const,
};
// 场景帧长（合计 1800 = 60s @ 30fps）
export const TIMING = {
  fps: 30,
  scenes: [135, 165, 210, 120, 270, 210, 300, 240, 150] as const,
  fade: 16,
  stagger: 14,
};
export const SCENE_STARTS: number[] = (() => {
  const acc: number[] = [];
  let t = 0;
  for (const d of TIMING.scenes) { acc.push(t); t += d; }
  return acc;
})();
export const TOTAL_FRAMES = TIMING.scenes.reduce((a, b) => a + b, 0);
// ---------- 文案 ----------
export const CONTENT = {
  brand: '鲸鲨漫剧',
  dayTag: '开发进度 · Day 1',
  hook: '我给自己写了个\n做短剧的软件',
  hookSub: '一句话进去，一部剧出来',
  idea: '讲一个普通人的一生，从1岁到100岁',
  ideaLabel: '在首页输入一句话',
  scriptTitle: 'AI 写出 3 集剧本',
  scriptSub: '八个人生阶段，8 个亮点',
  episodes: [
    { t: '一岁', d: '摔了才知道地是硬的' },
    { t: '五十岁', d: '上有老下有小' },
    { t: '一百岁', d: '下辈子还来这个家' },
  ],
  confirmTitle: '确认剧本\n你点头，才往下走',
  confirmSub: '每一步都有人把关',
  roleTitle: '同一个人的 5 个年龄段',
  roleSub: '定妆一次，全剧不换脸',
  shotTitle: '12 个镜头，按剧情排好',
  shotSub: '重要镜头和过场镜头分开算',
  frameTitle: '12 张画面，逐个真实生成',
  frameSub: '用的是我自己的模型账号',
  techTitle: '不是黑盒',
  techPoints: [
    { t: '调用全程可见', d: '每次请求都有日志' },
    { t: '密钥只留本机', d: '素材不经过第三方' },
    { t: '失败不计费', d: '废片不扣额度' },
  ],
  ctaTitle: '还在开发中',
  ctaSub: '每天更新一次进度',
  aiBadge: '本视频画面由 AI 生成',
};
// 真实分镜（来自引擎第 5 步确认的镜头表）
export const SHOTS = [
  '1岁：产房内婴儿第一声啼哭',
  '5岁：老巷子里踢毽子学步',
  '18岁：高考放榜日，少年在校门口',
  '22岁：拖着旧行李箱挤上绿皮火车',
  '30岁：筒朴婚礼现场，两家人握手',
  '35岁：深夜加班回家，轻掩房门',
  '50岁：医院长廊，手撑着膝盖',
  '60岁：退休最后一天，收回空工位',
  '70岁：老伴离世，独自坐在空房',
  '80岁：公园长椅上教孙子下棋',
  '95岁：轮椅上被推着晒太阳',
  '100岁：百岁寿宴，四世同堂',
];
// 12 张真实生成画面（engine/data/assets 落地后压缩）
export const FRAMES = Array.from({ length: 12 }, (_, i) =>
  `assets/frames/${String(i + 1).padStart(2, '0')}.jpg`);
// 5 张真实角色定妆图
export const ROLES = Array.from({ length: 5 }, (_, i) =>
  `assets/roles/${String(i + 1).padStart(2, '0')}.jpg`);
// 真实界面截图
export const SHOTS_UI = {
  script: 'assets/shots/step1-script.png',
  confirm: 'assets/shots/step2-confirm.png',
  roles: 'assets/shots/step3-roles.png',
};
export const BGM = 'sunbyrn_-_XPR.mp3';
// ============================================
