# -*- coding: utf-8 -*-
"""v3 改造：鳍形播放 logo + 全局小圆角 + 移除方角元素（L 角标/按钮切角）。幂等可重跑。"""
from PIL import Image
import base64, io, os, re
FIN_PATH = '<path d="M9 27C11 16.5 17 7.5 26 5c3.4-.9 6 .8 6 4.4V27Z" fill="currentColor" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>'
WAVE_PATH = '<path d="M4 33.5q4-3.5 8.5 0t8.5 0t8.5 0t8.5 0t6.5 0" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>'
LOGO_PAT = re.compile(r'<svg class="logo"[^>]*>.*?</svg>', re.S)
SHARK_PAT = re.compile(r"const shark='<svg.*?</svg>';", re.S)
FIN_DROP = re.compile(r'^\s*\.(?:card:before|\.player:before,\.player:after|player:before|player:after|'
                      r'hero-shot figure:before,\.hero-shot figure:after|hero-shot figure:before|'
                      r'hero-shot figure:after|step-cell:after)\{.*\}\s*$', re.M)
CLIP_PAT = re.compile(r'clip-path:polygon\([^)]*\)')
NEW_LOGO = ('<svg class="logo" width="27" height="23" viewBox="0 0 48 40" fill="none" aria-hidden="true">\n'
            '      ' + FIN_PATH + '\n'
            '      ' + WAVE_PATH + '\n'
            '    </svg>')
NEW_SHARK = ("const shark='<svg width=\"16\" height=\"13\" viewBox=\"0 0 48 40\" fill=\"none\" aria-hidden=\"true\">"
             + FIN_PATH.replace('stroke-width="1.6"', 'stroke-width="2"')
             + WAVE_PATH.replace('stroke-width="2.6"', 'stroke-width="3"')
             + "</svg>';")
ROUND_OVERRIDE = {'.card{': '10px', '.modal{': '12px', '.player{': '10px',
                  '.role{': '8px', '.side-foot{': '8px', '.toast{': '8px',
                  '.nav .nav-cta{': '8px'}
EXTRA_RADIUS = [
    ('.table img{', 'border-radius:3px'),
    ('.row img{', 'border-radius:3px'),
    ('.progress i{', 'border-radius:1.5px'),
    ('.status i{', 'border-radius:50%'),
    ('.mini-bars i{', 'border-radius:1px'),
    ('.settings h1:before{', 'border-radius:2px'),
    ('.stage em{', 'border-radius:4px'),
    ('.hero-tags span{', 'border-radius:4px'),
]
GRID_RADIUS = [
    ('.step-grid{', 'border-radius:10px;overflow:hidden'),
    ('.specs{', 'border-radius:10px;overflow:hidden'),
]
def add_prop(line, frag):
    """在 CSS 规则行尾 } 前追加属性；已存在则原样返回。"""
    if frag in line:
        return line
    stripped = line.rstrip()
    if stripped.endswith('}'):
        return stripped[:-1] + ';' + frag + '}'
    return line
def transform(path):
    s = open(path, encoding='utf-8').read()
    n1 = len(LOGO_PAT.findall(s))
    s = LOGO_PAT.sub(lambda m: NEW_LOGO, s)
    s = SHARK_PAT.sub(lambda m: NEW_SHARK, s)
    s = FIN_DROP.sub('', s)
    s = CLIP_PAT.sub('', s)
    out = []
    for line in s.split('\n'):
        if 'border-radius:var(--r)' in line:
            key = next((k for k in ROUND_OVERRIDE if line.startswith(k)), None)
            line = line.replace('border-radius:var(--r)', 'border-radius:' + ROUND_OVERRIDE.get(key, '6px'))
        for sel, frag in EXTRA_RADIUS:
            if line.startswith(sel):
                line = add_prop(line, frag)
        for sel, frag in GRID_RADIUS:
            if line.startswith(sel):
                line = add_prop(line, frag)
        out.append(line)
    s = '\n'.join(out)
    open(path, 'w', encoding='utf-8').write(s)
    print(path, 'logo replaced:', n1)
for p in ['_tpl_whale_app.html', '_tpl_whale_site.html']:
    transform(p)
print('done')
