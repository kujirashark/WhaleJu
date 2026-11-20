"""把已验证的 HTML 原型 + 桥接层打包成桌面壳前端。
原型文件本身不改动——后续原型迭代后重跑本脚本即可同步到桌面壳。
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "prototype" / "鲸鲨漫剧-制作台-v2.0.html"
OUT = ROOT / "desktop" / "frontend" / "index.html"
html = SRC.read_text(encoding="utf-8")
assert "</body>" in html, "原型结构异常：缺少 </body>"
assert "bridge.js" not in html, "原型已被注入过桥接脚本"
html = html.replace("</body>", '  <script src="bridge.js"></script>\n</body>')
OUT.write_text(html, encoding="utf-8")
print(f"生成桌面前端: {OUT} ({OUT.stat().st_size / 1024 / 1024:.2f} MB)")
