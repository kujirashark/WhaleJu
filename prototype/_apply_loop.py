# -*- coding: utf-8 -*-
"""业务闭环：作品库 + 充值 + 项目列表。幂等脚本。"""
import re
TPL = '_tpl_whale_app.html'
s = open(TPL, encoding='utf-8').read()
# ---------- 0. 幂等标记 ----------
if 'v-works' in s:
    print('already applied')
    raise SystemExit
# ---------- 1. 顶栏：加作品库页签 + 额度变充值入口 ----------
s = s.replace(
    '<button data-act="view" data-arg="work">制作</button>',
    '<button data-act="view" data-arg="work">制作</button>\n    <button data-act="view" data-arg="works">作品库</button>')
s = s.replace(
    '<div class="balance">额度 <b>86.4</b></div>',
    '<button class="balance" data-act="recharge" aria-label="充值额度">额度 <b>86.4</b></button>')
# ---------- 2. 首页：继续上次 → 我的项目（含已完成项目入口） ----------
s = s.replace(
    '<div class="home-sec">继续上次</div>',
    '<div class="home-sec">我的项目 · 2</div>')
s = s.replace(
    '''      <span class="chip c-run">4 / 8 步</span>
    </div>
  </div>''',
    '''      <span class="chip c-run">4 / 8 步</span>
    </div>
    <div class="proj" data-act="view" data-arg="works" role="button" tabindex="0" aria-label="打开作品库：都市逆袭">
      <img src="{{TEEN}}" alt="项目《都市逆袭》的成片封面">
      <div class="pi">
        <div class="t">都市逆袭 · 3 集</div>
        <div class="s">已完成 · 成片已导出到作品库</div>
        <div class="pbar2"><i style="width:100%"></i></div>
      </div>
      <span class="chip p-ok">已完成</span>
    </div>
  </div>''')
# ---------- 3. 新视图：作品库（插在设置视图之前） ----------
WORKS = '''<main id="v-works" class="view">
<div class="home">
  <div class="home-hero">
    <h1>作品库</h1>
    <p>导出的成片都存在这台电脑上。下载、复制发布文案，或者再剪一版。每一集都自动带 AI 生成标识和备案材料包。</p>
  </div>
  <div class="works">
    <div class="workcard">
      <div class="wshot"><img src="{{CHILD}}" alt="第 1 集成片封面"><span class="wt">01:12</span><span class="wk">AI 生成</span></div>
      <div class="wi">
        <div class="t">人的一生 · 第 1 集「院子」</div>
        <div class="s">竖屏 1080×1920 · 412 MB · 2026-11-17 导出</div>
        <div class="wacts">
          <button class="btn btn-p" data-act="download">下载</button>
          <button class="btn btn-s" data-act="copyCap" data-arg="第 1 集">复制发布文案</button>
          <button class="btn btn-s" data-act="redoShot">再剪一版</button>
        </div>
      </div>
    </div>
    <div class="workcard">
      <div class="wshot"><img src="{{TEEN}}" alt="第 2 集成片封面"><span class="wt">01:26</span><span class="wk">AI 生成</span></div>
      <div class="wi">
        <div class="t">人的一生 · 第 2 集「站台」</div>
        <div class="s">竖屏 1080×1920 · 466 MB · 2026-11-17 导出</div>
        <div class="wacts">
          <button class="btn btn-p" data-act="download">下载</button>
          <button class="btn btn-s" data-act="copyCap" data-arg="第 2 集">复制发布文案</button>
          <button class="btn btn-s" data-act="redoShot">再剪一版</button>
        </div>
      </div>
    </div>
    <div class="workcard">
      <div class="wshot"><img src="{{OLD}}" alt="第 3 集成片封面"><span class="wt">01:31</span><span class="wk">AI 生成</span></div>
      <div class="wi">
        <div class="t">人的一生 · 第 3 集「长椅」</div>
        <div class="s">竖屏 1080×1920 · 489 MB · 2026-11-17 导出</div>
        <div class="wacts">
          <button class="btn btn-p" data-act="download">下载</button>
          <button class="btn btn-s" data-act="copyCap" data-arg="第 3 集">复制发布文案</button>
          <button class="btn btn-s" data-act="redoShot">再剪一版</button>
        </div>
      </div>
    </div>
    <div class="workcard empty">
      <div class="wshot ph"></div>
      <div class="wi">
        <div class="t">下一个作品从这里开始</div>
        <div class="s">回首页用一句话新建项目，做完第 8 步就会出现在这里。</div>
        <div class="wacts"><button class="btn btn-s" data-act="view" data-arg="home">去新建</button></div>
      </div>
    </div>
  </div>
  <p class="home-note">发布提示：抖音 / 视频号 / B 站都要求勾选“AI 生成内容”，文案里已经帮你写好了声明。</p>
</div>
</main>
'''
anchor = '<main id="v-settings" class="view">'
assert anchor in s
s = s.replace(anchor, WORKS + anchor, 1)
# ---------- 4. 充值弹窗（独立 overlay，插在现有 modal 之后） ----------
PAY = '''
<div class="ov" id="pay" role="dialog" aria-modal="true" aria-label="充值额度">
  <div class="modal">
    <div class="modal-h">充值额度</div>
    <div class="modal-b">额度用来生成画面和视频。平台额度不用注册模型账号；如果你有自己的密钥，生成不消耗额度。</div>
    <div class="plans" id="plans">
      <button class="plan sel" data-act="paySel" data-arg="p1"><span class="pt">试用包</span><span class="pv">¥49 · 50 额度</span><span class="pd">够做 1 集，先试试</span></button>
      <button class="plan" data-act="paySel" data-arg="p2"><span class="pt">创作月包</span><span class="pv">¥99 · 200 额度</span><span class="pd">3 集 × 2 轮返工</span></button>
      <button class="plan" data-act="paySel" data-arg="p3"><span class="pt">年度包</span><span class="pv">¥299 · 1000 额度</span><span class="pd">长期创作最划算</span></button>
    </div>
    <div class="modal-f">
      <button class="btn btn-s" data-act="closePay">先不用</button>
      <button class="btn btn-p" data-act="payConfirm">确认支付</button>
    </div>
  </div>
</div>
'''
manchor = '<div class="ov" id="modal" role="dialog" aria-modal="true">'
assert manchor in s
s = s.replace(manchor, PAY.strip() + '\n' + manchor, 1)
# ---------- 5. CSS ----------
CSS = '''
/* ===== 业务闭环：作品库 / 充值 / 项目列表 ===== */
.balance{background:none;border:none;color:var(--ink2);font:inherit;font-size:11.5px;letter-spacing:.04em;cursor:pointer;padding:6px 10px;border-radius:6px;font-family:var(--font)}
.balance:hover{background:var(--accent-soft);color:var(--accent)}
.balance b{color:var(--ink);font-variant-numeric:tabular-nums}
.works{display:grid;grid-template-columns:1fr 1fr;gap:16px;max-width:880px;margin:0 auto;width:100%}
.workcard{display:flex;gap:14px;background:var(--panel);border-radius:10px;padding:14px;box-shadow:0 18px 34px -18px rgba(0,0,0,.55);align-items:stretch}
.workcard.empty{align-items:center}
.wshot{position:relative;width:96px;min-height:128px;border-radius:8px;overflow:hidden;flex-shrink:0}
.wshot img{width:100%;height:100%;object-fit:cover}
.wshot.ph{background:var(--panel2);border:1px dashed var(--line2);display:grid;place-items:center}
.wt{position:absolute;left:6px;bottom:6px;background:rgba(4,18,28,.82);color:#fff;font-size:10px;padding:2px 6px;border-radius:4px;font-variant-numeric:tabular-nums}
.wk{position:absolute;right:6px;top:6px;background:var(--accent-soft);color:var(--accent);font-size:9.5px;padding:2px 6px;border-radius:4px;border:1px solid var(--accent-line)}
.wi{display:flex;flex-direction:column;gap:6px;flex:1;min-width:0}
.wi .t{font-size:13px;color:var(--ink);font-weight:600}
.wi .s{font-size:11.5px;color:var(--ink3);line-height:1.5}
.wacts{display:flex;gap:8px;margin-top:auto;flex-wrap:wrap}
.plans{display:flex;flex-direction:column;gap:8px;margin:12px 0 4px}
.plan{display:grid;grid-template-columns:auto auto 1fr;gap:4px 12px;align-items:baseline;text-align:left;background:var(--panel2);border:1px solid transparent;border-radius:8px;padding:10px 14px;cursor:pointer;font-family:var(--font);transition:border-color .15s,background .15s}
.plan:hover{background:var(--accent-soft)}
.plan.sel{border-color:var(--accent);background:var(--accent-soft)}
.plan .pt{font-size:13px;font-weight:600;color:var(--ink)}
.plan .pv{font-size:12.5px;color:var(--accent);font-variant-numeric:tabular-nums}
.plan .pd{font-size:11.5px;color:var(--ink3);text-align:right}
'''
s = s.replace('</style>', CSS + '</style>', 1)
# ---------- 6. act() 扩展 ----------
s = s.replace(
    '''    ["home","work","settings"].forEach(v=>{const el=$("#v-"+v); if(el) el.classList.toggle("on",arg===v);});''',
    '''    ["home","work","works","settings"].forEach(v=>{const el=$("#v-"+v); if(el) el.classList.toggle("on",arg===v);});''')
s = s.replace(
    '''    $("#crumb").innerHTML = arg==="home" ? "首页" : (arg==="settings" ? "设置" : '项目 / <b>人的一生</b> · 第 1 集');''',
    '''    $("#crumb").innerHTML = arg==="home" ? "首页" : (arg==="works" ? "作品库" : (arg==="settings" ? "设置" : '项目 / <b>人的一生</b> · 第 1 集'));''')
s = s.replace(
    '''  if(a==="download"){ toast("已保存到「人的一生 / 导出」文件夹"); return; }''',
    '''  if(a==="download"){ toast("已保存到本地「作品库」文件夹"); return; }
  if(a==="copyCap"){ toast(arg + "发布文案已复制，含 AI 生成声明"); return; }
  if(a==="recharge"){ $("#pay").classList.add("open"); return; }
  if(a==="closePay"){ $("#pay").classList.remove("open"); return; }
  if(a==="paySel"){ S.plan=arg; document.querySelectorAll(".plan").forEach(x=>x.classList.toggle("sel",x.dataset.arg===arg)); return; }
  if(a==="payConfirm"){ $("#pay").classList.remove("open");
    const add={p1:50,p2:200,p3:1000}[S.plan]||50;
    S.credits=(S.credits||86.4)+add;
    document.querySelector(".balance b").textContent=S.credits.toFixed(1);
    toast("充值成功，额度已到账 +" + add); return; }''')
s = s.replace(
    '''    if(S.exp.pct>=100){ S.exp.pct=100; S.exp.state="done"; clearInterval(t); renderStream(); toast("导出完成，可以下载了"); return; }''',
    '''    if(S.exp.pct>=100){ S.exp.pct=100; S.exp.state="done"; clearInterval(t); renderStream(); toast("导出完成，已存入作品库"); return; }''')
# 第 8 步完成后 → 去作品库
s = s.replace(
    '''          ${e.state==="done"?`<button class="btn btn-p" data-act="download">下载视频</button><button class="btn btn-s" data-act="doExport">重新导出</button>`:""}''',
    '''          ${e.state==="done"?`<button class="btn btn-p" data-act="download">下载视频</button><button class="btn btn-s" data-act="view" data-arg="works">去作品库</button><button class="btn btn-s" data-act="doExport">重新导出</button>`:""}''')
open(TPL, 'w', encoding='utf-8').write(s)
print('loop closure applied')
