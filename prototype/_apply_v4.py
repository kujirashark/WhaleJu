# -*- coding: utf-8 -*-
"""v4 柔化：去网格纹理、实线边框软化、选中态改背景色。幂等可重跑。"""
import re
SOFTEN = [
    # 分割线体系整体调淡（深/浅两套）
    ('--line:#1d2a3c; --line2:#2a3b52;', '--line:rgba(140,180,225,.10); --line2:rgba(140,180,225,.17);'),
    ('--line:#cddae7; --line2:#a9bed2;', '--line:rgba(20,80,130,.10); --line2:rgba(20,80,130,.17);'),
    # 工作台 body 网格背景移除
    ('''  background-color:var(--bg);
  background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);
  background-size:28px 28px;''', '  background:var(--bg);'),
    # 选中态：背景色区分，不再用彩色实线框
    ('.ch.sel{border-color:var(--accent);background:var(--accent-soft)}', '.ch.sel{background:var(--accent-soft)}'),
    ('.ch:hover{border-color:var(--accent-line)}', '.ch:hover{background:var(--panel2)}'),
    ('.ch:hover{border-color:var(--accent-line);color:var(--accent)}', '.ch:hover{background:var(--panel2)}'),
    ('.role.sel{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}', '.role.sel{box-shadow:0 0 0 2px var(--accent)}'),
    # 状态标签去实线框
    ('border-color:var(--ok)!important;', ''),
    ('border-color:var(--warn)!important;', ''),
    ('border-color:var(--ok)!important', ''),
    ('border-color:var(--accent-line)!important;', ''),
    ('border-color:var(--danger)!important;', ''),
    ('border-color:var(--ok);', ''),
    ('border-color:var(--accent);', ''),
    ('border-color:var(--danger);', ''),
    ('border-color:var(--key);', ''),
    # 图标按钮去边框，hover 改背景
    ('.icobtn:hover{border-color:var(--accent);color:var(--accent)}', '.icobtn:hover{color:var(--accent);background:var(--panel2)}'),
    ('.nav .icobtn:hover{border-color:var(--accent);color:var(--accent)}', '.nav .icobtn:hover{color:var(--accent);background:var(--panel2)}'),
]
DROP_BORDER = re.compile(r'border:1px solid var\((?:line|line2|accent-line|accent|line2)\);?')
GRID_BLOCKS_SITE = [
    re.compile(r'\.hero:before\{.*?\}\s*', re.S),
    re.compile(r'\.hero:after\{.*?\}\s*', re.S),
    re.compile(r'^\.dark:before\{.*\}\s*$', re.M),
    re.compile(r'^\.cta-band:before\{.*\}\s*$', re.M),
]
def transform(path, is_site):
    s = open(path, encoding='utf-8').read()
    for a, b in SOFTEN:
        s = s.replace(a, b)
    s = DROP_BORDER.sub('', s)
    if is_site:
        for pat in GRID_BLOCKS_SITE:
            s = pat.sub('', s)
    # 清理连续分号与空属性
    s = re.sub(r';{2,}', ';', s)
    s = re.sub(r'\{\s*;\}', '{}', s)
    s = re.sub(r';\}', '}', s)
    open(path, 'w', encoding='utf-8').write(s)
    print(path, 'softened')
transform('_tpl_whale_app.html', False)
transform('_tpl_whale_site.html', True)
print('done')
