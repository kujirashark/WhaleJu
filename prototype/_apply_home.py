# -*- coding: utf-8 -*-
"""为制作台补首页视图：默认打开首页，三页签闭环。幂等（按锚点检查）。"""
import re
HOME_CSS = """
/* ---------- 首页 ---------- */
.home{height:calc(100vh - 46px);overflow-y:auto;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px 24px;text-align:center}
.home-hero h1{font-size:28px;font-weight:700;letter-spacing:.01em}
.home-hero p{margin-top:10px;color:var(--ink2);font-size:13px;max-width:520px}
.home-box{margin-top:26px;width:min(640px,100%);background:var(--panel);border-radius:12px;box-shadow:0 24px 50px -24px rgba(0,0,0,.55);padding:14px 14px 12px;text-align:left}
.home-box textarea{width:100%;border:none;background:transparent;resize:none;color:var(--ink);font-family:inherit;font-size:13.5px;line-height:1.6;outline:none}
.home-box textarea::placeholder{color:var(--ink3)}
.home-box-ft{display:flex;align-items:center;gap:8px;margin-top:12px}
.home-box-ft .chips{display:flex;gap:6px;flex-wrap:wrap}
.home-box-ft .btn-p{margin-left:auto}
.home-recent{margin-top:46px;width:min(640px,100%);text-align:left}
.home-sec{font-family:var(--mono);font-size:10px;letter-spacing:.12em;color:var(--ink3);margin-bottom:10px}
.proj{display:flex;gap:12px;align-items:center;background:var(--panel);border-radius:10px;padding:12px;cursor:pointer;box-shadow:0 18px 36px -22px rgba(0,0,0,.55);transition:box-shadow .25s}
.proj:hover{box-shadow:0 26px 46px -20px rgba(0,0,0,.65)}
.proj img{width:64px;height:40px;object-fit:cover;border-radius:6px}
.proj .pi{flex:1;min-width:0}
.proj .t{font-size:13px;font-weight:600}
.proj .s{font-size:11px;color:var(--ink3);margin-top:3px}
.pbar2{height:4px;background:var(--panel2);border-radius:2px;margin-top:8px;overflow:hidden}
.pbar2 i{display:block;height:100%;background:var(--accent)}
.home-note{margin-top:26px;font-size:11px;color:var(--ink3);max-width:560px}
@media (max-width:1024px){.home{padding:28px 16px}}
"""
HOME_HTML = """<main id="v-home" class="view on">
<div class="home">
  <div class="home-hero">
    <h1>今天，想做一部什么剧？</h1>
    <p>一句话描述你的想法，助手带你从剧本走到成片。你只需要在三件事上确认：剧本、角色、前 30 秒。</p>
  </div>
  <div class="home-box">
    <textarea id="idea" rows="2" placeholder="例如：讲一个普通人的一生，从八岁到七十岁，三集竖屏短剧" aria-label="描述你想做的剧"></textarea>
    <div class="home-box-ft">
      <div class="chips">
        <button class="chip c-run" data-act="fillTpl" data-arg="life">普通人的一生</button>
        <button class="chip" data-act="fillTpl" data-arg="city">都市逆袭</button>
        <button class="chip" data-act="fillTpl" data-arg="mystery">悬疑反转</button>
      </div>
      <button class="btn btn-p" data-act="create">开始创作</button>
    </div>
  </div>
  <div class="home-recent">
    <div class="home-sec">继续上次</div>
    <div class="proj" data-act="openProject" role="button" tabindex="0" aria-label="打开项目：人的一生">
      <img src="{{HERO}}" alt="项目《人的一生》的示例剧照">
      <div class="pi">
        <div class="t">人的一生 · 3 集</div>
        <div class="s">上次做到：第 4 步 · 确认角色形象</div>
        <div class="pbar2"><i style="width:50%"></i></div>
      </div>
      <span class="chip c-run">4 / 8 步</span>
    </div>
  </div>
  <p class="home-note">密钥和素材只存在你的电脑上，调用直接发给模型厂商。没有模型也能先用平台额度试做第一集。</p>
</div>
</main>
"""
s = open('_tpl_whale_app.html', encoding='utf-8').read()
changed = []
if 'id="v-home"' not in s:
    # 1) 首页视图插入在 v-work 之前
    a = '<main id="v-work" class="view on">'
    assert a in s
    s = s.replace(a, HOME_HTML + '<main id="v-work" class="view">', 1)
    changed.append('home view')
    # 2) CSS 追加
    a = '@media (max-width:1024px){.side{width:196px}.right{width:262px}.stream{padding:16px}}'
    assert a in s
    s = s.replace(a, HOME_CSS + a, 1)
    changed.append('home css')
    # 3) 顶栏 seg 三页签，首页默认
    a = '''  <nav class="seg" aria-label="页面">
    <button class="on" data-act="view" data-arg="work">制作</button>
    <button data-act="view" data-arg="settings">模型设置</button>
  </nav>'''
    b = '''  <nav class="seg" aria-label="页面">
    <button class="on" data-act="view" data-arg="home">首页</button>
    <button data-act="view" data-arg="work">制作</button>
    <button data-act="view" data-arg="settings">模型设置</button>
  </nav>'''
    assert a in s
    s = s.replace(a, b, 1)
    changed.append('seg tabs')
    # 4) crumb 加 id 便于切换
    a = '<div class="crumb">项目 / <b>人的一生</b> · 第 1 集</div>'
    b = '<div class="crumb" id="crumb">首页</div>'
    assert a in s
    s = s.replace(a, b, 1)
    changed.append('crumb')
    # 5) JS：默认视图与三视图切换
    a = "  step:3, view:\"work\", tab:\"shots\", locked:false,"
    b = "  step:3, view:\"home\", tab:\"shots\", locked:false,"
    assert a in s
    s = s.replace(a, b, 1)
    changed.append('default view')
    a = '''  if(a==="view"){ S.view=arg; $("#v-work").classList.toggle("on",arg==="work"); $("#v-settings").classList.toggle("on",arg==="settings");
    document.querySelectorAll('.seg button').forEach(b=>b.classList.toggle("on",b.dataset.arg===arg)); return; }'''
    b = '''  if(a==="view"){ S.view=arg;
    ["home","work","settings"].forEach(v=>{const el=$("#v-"+v); if(el) el.classList.toggle("on",arg===v);});
    document.querySelectorAll('.seg button').forEach(b=>b.classList.toggle("on",b.dataset.arg===arg));
    $("#crumb").innerHTML = arg==="home" ? "首页" : (arg==="settings" ? "设置" : '项目 / <b>人的一生</b> · 第 1 集');
    return; }
  if(a==="create"){ const v=$("#idea").value.trim();
    if(!v){ toast("先写一句你的想法，或者点下面的题材模板"); $("#idea").focus(); return; }
    S.view="work"; S.step=0; render(); $("#v-home").classList.remove("on"); $("#v-work").classList.add("on");
    document.querySelectorAll('.seg button').forEach(b=>b.classList.toggle("on",b.dataset.arg==="work"));
    $("#crumb").innerHTML='项目 / <b>人的一生</b> · 第 1 集';
    toast("已按你的想法写第一稿大纲，看看第 1 步"); return; }
  if(a==="openProject"){ S.view="work"; render();
    $("#v-home").classList.remove("on"); $("#v-work").classList.add("on");
    document.querySelectorAll('.seg button').forEach(b=>b.classList.toggle("on",b.dataset.arg==="work"));
    $("#crumb").innerHTML='项目 / <b>人的一生</b> · 第 1 集';
    toast("已打开「人的一生」，从上次的地方继续"); return; }
  if(a==="fillTpl"){ const m={life:"讲一个普通人的一生，从八岁到七十岁，三集竖屏短剧",
    city:"都市逆袭：被裁员的中年程序员靠 AI 重新翻身，三集",
    mystery:"深夜便利店连续出现同一张脸，悬疑三集"};
    $("#idea").value=m[arg]||""; $("#idea").focus(); return; }'''
    assert a in s
    s = s.replace(a, b, 1)
    changed.append('act branches')
    # 6) view 切换时若离开 work 无需暂停生成（生成计时器独立，保持）
open('_tpl_whale_app.html', 'w', encoding='utf-8').write(s)
print('applied:', ', '.join(changed) if changed else 'already applied (idempotent)')
