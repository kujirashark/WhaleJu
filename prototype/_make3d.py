# -*- coding: utf-8 -*-
"""在现有 FLAT-TECH 原型上叠加 3D 空间层，生成 v2.0 模板。"""
from PIL import Image
import base64, io, os
CSS_APP = r"""
/* ========== FLAT-TECH 3D 空间层 ========== */
:root{--px:0deg;--py:0deg}
html,body{height:100%}
body{perspective:1700px;perspective-origin:50% 42%;overflow-x:hidden;transition:perspective .4s}
body.flat{perspective:none}
body.flat *,body.flat *::before,body.flat *::after{transform:none!important}
body.flat .player{box-shadow:0 12px 32px -14px rgba(0,0,0,.6)!important}
body.flat .hero-shot figure{box-shadow:0 24px 50px -24px rgba(0,0,0,.8)!important}
.topbar{position:relative;z-index:35}
.btn3d{color:var(--accent)}
body.flat .btn3d{color:var(--ink3)}
.bench{
  transform-style:preserve-3d;
  transform:rotateX(calc(3.5deg + var(--py,0deg))) rotateY(calc(-2.5deg + var(--px,0deg)));
  transform-origin:50% 28%;
  transition:transform .35s cubic-bezier(.22,.8,.25,1);
}
/* 重要：三栏与其内部均为滚动容器，Chrome 会把 overflow 容器内的 3D 子树扁平化。
   对它们施加 translateZ 会让「渲染位置」与「点击命中」错位（实测点按钮命中父容器）。
   因此工作台只在整体场景层做真实 3D 旋转，元素厚度一律用分层阴影表达。 */
.side{box-shadow:14px 0 34px -20px rgba(0,0,0,.75)}
.right{box-shadow:-14px 0 34px -20px rgba(0,0,0,.75)}
.side .st{transition:box-shadow .25s ease,background .25s ease}
.side .st.done .mk{box-shadow:0 0 8px rgba(47,224,138,.25)}
.side .st.now{box-shadow:8px 10px 26px -10px rgba(0,0,0,.9)}
.side .st.now .mk{box-shadow:0 0 12px var(--accent-line)}
.card{
  box-shadow:0 36px 64px -20px rgba(0,0,0,.88);
  transition:box-shadow .35s ease;
}
.card:hover{box-shadow:0 46px 80px -16px rgba(0,0,0,.94)}
.acts .btn{transition:filter .15s,border-color .15s,color .15s}
.acts .btn:hover{filter:brightness(1.12)}
.role{transition:box-shadow .35s}
.role.sel{box-shadow:0 16px 26px -12px rgba(0,0,0,.7),inset 0 0 0 1px var(--accent)}
.role:hover{box-shadow:0 22px 36px -12px rgba(0,0,0,.8);z-index:3}
.table tbody tr{transition:background .2s}
.table tbody tr:hover{background:var(--panel2)}
.progress i.on{box-shadow:0 0 12px var(--accent-line),0 2px 6px rgba(0,0,0,.5)}
/* 播放器厚度用两层偏移阴影表达，不依赖 translateZ */
.player{box-shadow:0 26px 50px -16px rgba(0,0,0,.85),18px 18px 0 var(--panel2),19px 19px 0 var(--line2)}
.right .row{transition:background .2s}
.right .row:hover{background:var(--panel2)}
.ch{transition:border-color .15s,background .15s}
.modal{box-shadow:0 40px 90px -24px rgba(0,0,0,.9)}
"""
CSS_SITE = r"""
/* ========== FLAT-TECH 3D 空间层 ========== */
:root{--px:0deg;--py:0deg}
html,body{height:100%}
body{perspective:1500px;perspective-origin:50% 30%;overflow-x:hidden;transition:perspective .4s}
body.flat{perspective:none}
body.flat *,body.flat *::before,body.flat *::after{transform:none!important}
body.flat .player{box-shadow:0 12px 32px -14px rgba(0,0,0,.6)!important}
body.flat .hero-shot figure{box-shadow:0 24px 50px -24px rgba(0,0,0,.8)!important}
.nav{transform-style:preserve-3d;transform:translateZ(38px);box-shadow:0 12px 30px -20px rgba(0,0,0,.85)}
.btn3d{color:var(--accent)}
body.flat .btn3d{color:var(--ink3)}
.hero{transform-style:preserve-3d;perspective:1200px}
.hero .wrap{transform:translateZ(70px) rotateY(calc(var(--px,0deg) * .25)) rotateX(calc(var(--py,0deg) * .25));transition:transform .35s cubic-bezier(.22,.8,.25,1)}
.hero-shot{transform-style:preserve-3d}
.hero-shot figure{
  transform:translateZ(30px) rotateX(3deg) rotateY(calc(var(--px,0deg) * .18));
  box-shadow:0 54px 90px -28px rgba(0,0,0,.9),16px 16px 0 var(--panel2),17px 17px 0 var(--line);
  transition:transform .4s cubic-bezier(.22,.8,.25,1);
}
.stages,.step-grid,.specs{transform-style:preserve-3d}
.stage{transform:translateZ(0);transition:transform .35s cubic-bezier(.22,.8,.25,1),box-shadow .35s}
.stage:hover{transform:translateZ(34px) rotateY(-6deg);box-shadow:0 22px 38px -14px rgba(0,0,0,.8);z-index:2}
.step-grid{transform:rotateX(6deg) rotateY(-4deg);transform-origin:50% 50%}
.stages{transform:rotateX(3deg)}
.specs{transform:rotateX(4deg) rotateY(-2deg)}
.step-cell{transform:translateZ(0);transition:transform .3s cubic-bezier(.22,.8,.25,1),box-shadow .3s}
.step-cell:hover{transform:translateZ(36px) rotateX(-3deg);box-shadow:0 22px 40px -16px rgba(0,0,0,.75);z-index:2}
.step-cell:after{transform:translateZ(2px)}
.feature img{transform:translateZ(26px) rotateY(2.5deg);box-shadow:0 30px 60px -24px rgba(0,0,0,.8);transition:transform .4s}
.feature.rev img{transform:translateZ(26px) rotateY(-2.5deg)}
.feature img:hover{transform:translateZ(44px) rotateY(0deg)}
.dark{transform-style:preserve-3d}
.dark-shot{transform:translateZ(24px) rotateX(2.5deg);box-shadow:0 40px 70px -30px rgba(0,0,0,.9)}
.spec{transform:translateZ(0);transition:transform .3s,box-shadow .3s}
.spec:hover{transform:translateZ(26px);box-shadow:0 16px 30px -12px rgba(0,0,0,.6);z-index:2}
.cta-band{transform-style:preserve-3d}
.cta-band .wrap{transform:translateZ(24px)}
"""
PARALLAX = r"""
/* 3D 视差与平面降级 */
(function(){
  var root=document.documentElement, body=document.body;
  var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(reduce) body.classList.add('flat');
  var btn=document.getElementById('dim3dBtn');
  function sync(){
    if(!btn) return;
    var flat=body.classList.contains('flat');
    btn.innerHTML=flat
      ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="3" width="18" height="18" rx="1"/></svg>'
      : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M12 2 21 7v10l-9 5-9-5V7l9-5Z"/><path d="m3 7 9 5 9-5M12 12v10"/></svg>';
    btn.setAttribute('aria-label',flat?'切换到 3D 视角':'切换到平面视图');
    btn.setAttribute('title',flat?'切换到 3D 视角':'切换到平面视图');
    if(flat){root.style.setProperty('--px','0deg');root.style.setProperty('--py','0deg');}
  }
  if(btn && !btn.dataset.bound){
    btn.dataset.bound='1';
    btn.addEventListener('click',function(e){
      e.stopPropagation();
      body.classList.toggle('flat');
      sync();
    });
  }
  sync();
  var raf=0;
  document.addEventListener('mousemove',function(e){
    if(body.classList.contains('flat')||raf) return;
    raf=requestAnimationFrame(function(){
      var x=(e.clientX/window.innerWidth-.5)*2, y=(e.clientY/window.innerHeight-.5)*2;
      root.style.setProperty('--px',(x*3).toFixed(2)+'deg');
      root.style.setProperty('--py',(-y*2).toFixed(2)+'deg');
      raf=0;
    });
  },{passive:true});
})();
"""
BTN = ('<button class="icobtn btn3d" id="dim3dBtn" aria-label="切换到平面视图" '
       'title="切换到平面视图"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
       'stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M12 2 21 7v10l-9 5-9-5V7l9-5Z"/>'
       '<path d="m3 7 9 5 9-5M12 12v10"/></svg></button> ')
def build(src, css, out_tpl, out_html, imgmap, app=False):
    s = open(src, encoding='utf-8').read()
    assert '</style>' in s and '</script>' in s
    s = s.replace('</style>', css + '\n</style>', 1)
    s = s.replace('</script>', '\n' + PARALLAX + '\n</script>', 1)
    if app:
        anchor = '<button class="icobtn" data-act="theme"'
        assert anchor in s
        s = s.replace(anchor, BTN + anchor, 1)
        # act() 内增加 dim3d 分支（按钮由独立监听器处理，这里兜底）
        s = s.replace('  if(a==="theme"){', '  if(a==="dim3d"){ document.body.classList.toggle("flat"); toast(document.body.classList.contains("flat")?"已切换到平面视图":"已切换到 3D 视角"); return; }\n  if(a==="theme"){', 1)
    else:
        anchor = '<button class="icobtn" id="themeBtn"'
        assert anchor in s
        s = s.replace(anchor, BTN + anchor, 1)
    open(out_tpl, 'w', encoding='utf-8').write(s)
    for k, v in imgmap.items():
        s = s.replace('{{' + k + '}}', v)
    open(out_html, 'w', encoding='utf-8').write(s)
    print(out_tpl, '->', out_html, round(os.path.getsize(out_html) / 1024 / 1024, 2), 'MB')
def data_uri(path, maxw, q=82):
    im = Image.open(path).convert('RGB')
    w, h = im.size
    if w > maxw:
        im = im.resize((maxw, int(h * maxw / w)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=q, optimize=True, progressive=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
imgs = {
    'HERO': data_uri('assets/hero.jpg', 1200),
    'CHILD': data_uri('assets/child.jpg', 620),
    'TEEN': data_uri('assets/teen.jpg', 620),
    'ADULT': data_uri('assets/adult.jpg', 620),
    'MID': data_uri('assets/mid.jpg', 620),
    'OLD': data_uri('assets/old.jpg', 620),
}
build('_tpl_whale_app.html', CSS_APP, '_tpl_whale3d_app.html',
      '鲸鲨漫剧-制作台-v2.0.html', imgs, app=True)
build('_tpl_whale_site.html', CSS_SITE, '_tpl_whale3d_site.html',
      '鲸鲨漫剧-官网-v2.0.html', imgs, app=False)
