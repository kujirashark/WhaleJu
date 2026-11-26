/** 原型常量原样迁移：素材、步骤、角色、镜头表。改内容只改这里。 */
export const IMG = {
  child: './assets/child.jpg',
  teen: './assets/teen.jpg',
  adult: './assets/adult.jpg',
  mid: './assets/mid.jpg',
  old: './assets/old.jpg',
  hero: './assets/hero.jpg',
}

export const STEPS = [
  { n: '写剧本', d: '按你说的集数写' },
  { n: '确认剧本', d: '你确认后才继续' },
  { n: '角色形象', d: '5 个年龄' },
  { n: '确认角色形象', d: '必须你确认' },
  { n: '拆分镜头', d: '12 个镜头' },
  { n: '生成画面', d: '消耗你自己的厂商额度' },
  { n: '看成片', d: '前 30 秒' },
  { n: '导出视频', d: '竖屏 MP4' },
]

export const ROLES = [
  { k: 'child', name: '八岁', img: IMG.child },
  { k: 'teen', name: '十八岁', img: IMG.teen },
  { k: 'adult', name: '二十八岁', img: IMG.adult },
  { k: 'mid', name: '四十五岁', img: IMG.mid },
  { k: 'old', name: '七十岁', img: IMG.old },
]

export interface Shot { i: number; t: string; img: string; key: boolean; model: string; cost: number }
export const SHOTS: Shot[] = [
  { i: 1, t: '院子里 · 童年跑过', img: IMG.child, key: true, model: '可灵（你的密钥）', cost: 16 },
  { i: 2, t: '晾衣绳 · 空镜', img: IMG.child, key: false, model: '海螺 AI', cost: 9 },
  { i: 3, t: '站台 · 少年回头', img: IMG.teen, key: true, model: '可灵（你的密钥）', cost: 16 },
  { i: 4, t: '绿皮车 · 窗边', img: IMG.teen, key: false, model: '海螺 AI', cost: 9 },
  { i: 5, t: '写字楼 · 深夜加班', img: IMG.adult, key: true, model: '可灵（你的密钥）', cost: 16 },
  { i: 6, t: '街边 · 一碗面', img: IMG.adult, key: false, model: '海螺 AI', cost: 9 },
  { i: 7, t: '医院 · 走廊长椅', img: IMG.mid, key: true, model: '可灵（你的密钥）', cost: 16 },
  { i: 8, t: '病房 · 光', img: IMG.mid, key: false, model: '海螺 AI', cost: 9 },
  { i: 9, t: '老屋 · 门廊', img: IMG.hero, key: true, model: '可灵（你的密钥）', cost: 16 },
  { i: 10, t: '公园 · 长椅', img: IMG.old, key: false, model: '海螺 AI', cost: 9 },
  { i: 11, t: '夕阳 · 大远景', img: IMG.old, key: false, model: '海螺 AI', cost: 9 },
  { i: 12, t: '背影 · 定格', img: IMG.old, key: true, model: '可灵（你的密钥）', cost: 16 },
]

export const TEMPLATES: Record<string, string> = {
  life: '讲一个普通人的一生，从八岁到七十岁，三集竖屏短剧',
  city: '都市逆袭：被裁员的中年程序员靠 AI 重新翻身，三集',
  mystery: '深夜便利店连续出现同一张脸，悬疑三集',
}
