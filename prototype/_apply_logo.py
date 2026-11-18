# -*- coding: utf-8 -*-
"""把 C1 分镜播放 logo 应用到所有模板，并重建 v1/v2 HTML。"""
from PIL import Image
import base64, io, os, re
OLD_PATHS = [
    '<path d="M2 14.5C7 8.5 18 6.5 28.5 11L38 5.5L35 13L38 20L28.5 15C18 19.5 7 19 2 14.5Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
    '<path d="M17 8.2L19.5 3L23 8.9" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
    '<circle cx="8.5" cy="13" r="1" fill="currentColor"/>',
]
NEW_PATHS = [
    '<path d="M8 5h40l7 7v20l-7 7H8l-7-7V12Z" stroke="currentColor" stroke-width="1.6" opacity=".45"/>',
    '<path d="M48 5v7h7" stroke="currentColor" stroke-width="1.6" opacity=".45"/>',
    '<path d="M12 16l8 11 6-6" stroke="currentColor" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>',
    '<path d="M26 18l12 6-12 6Z" fill="currentColor"/>',
    '<path d="M38 21l6 6 8-11" stroke="currentColor" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>',
]
OLD_SHARK_PAT = re.compile(
    r"const shark='<svg width=\"16\" height=\"11\" viewBox=\"0 0 40 26\".*?</svg>';")
NEW_SHARK = ('const shark=\'<svg width="16" height="11" viewBox="0 0 60 40" fill="none" aria-hidden="true">'
             '<path d="M8 5h40l7 7v20l-7 7H8l-7-7V12Z" stroke="currentColor" stroke-width="2" opacity=".4"/>'
             '<path d="M12 16l8 11 6-6" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'
             '<path d="M26 18l12 6-12 6Z" fill="currentColor"/>'
             '<path d="M38 21l6 6 8-11" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'
             '</svg>\';')
LOGO_PAT = re.compile(
    r'<svg class="logo"[^>]*viewBox="0 0 40 26"[^>]*>.*?</svg>', re.S)
def new_logo(indent):
    lines = ['<svg class="logo" width="28" height="19" viewBox="0 0 60 40" fill="none" aria-hidden="true">']
    lines += [indent + p for p in NEW_PATHS]
    lines.append(indent.replace('  ', '', 1) + '</svg>' if False else indent[:-2] + '</svg>')
    return '\n'.join(lines)
for path in ['_tpl_whale_app.html', '_tpl_whale_site.html']:
    s = open(path, encoding='utf-8').read()
    def repl(m):
        block = m.group(0)
        first_nl = block.find('\n')
        indent = block[first_nl + 1: first_nl + 1 + (len(block[first_nl + 1:]) - len(block[first_nl + 1:].lstrip()))]
        return new_logo(indent)
    s, n = LOGO_PAT.subn(repl, s)
    s, k = OLD_SHARK_PAT.subn(NEW_SHARK, s)
    open(path, 'w', encoding='utf-8').write(s)
    print(path, 'logo:', n, 'shark:', k)
    remaining = s.count('viewBox="0 0 40 26"')
    print(path, 'old logo remaining:', remaining)
def data_uri(path, maxw, q=82):
    im = Image.open(path).convert('RGB'); w, h = im.size
    if w > maxw: im = im.resize((maxw, int(h * maxw / w)), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=q, optimize=True, progressive=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
imgs = {
    'HERO': data_uri('assets/hero.jpg', 1200),
    'CHILD': data_uri('assets/child.jpg', 620),
    'TEEN': data_uri('assets/teen.jpg', 620),
    'ADULT': data_uri('assets/adult.jpg', 620),
    'MID': data_uri('assets/mid.jpg', 620),
    'OLD': data_uri('assets/old.jpg', 620),
}
for tpl, out in [('_tpl_whale_app.html', '鲸鲨漫剧-制作台-v1.0.html'),
                 ('_tpl_whale_site.html', '鲸鲨漫剧-官网-v1.0.html')]:
    s = open(tpl, encoding='utf-8').read()
    for k, v in imgs.items(): s = s.replace('{{' + k + '}}', v)
    open(out, 'w', encoding='utf-8').write(s)
    print('rebuilt', out, round(os.path.getsize(out) / 1024 / 1024, 2), 'MB')
