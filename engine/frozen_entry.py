"""PyInstaller 打包入口：桌面安装包内的引擎由这个文件编译为 whaleju-engine.exe。

与 engine/run.py 的区别：
- run.py 面向源码运行（uvicorn 字符串引用 + 端口占用人话提示）；
- frozen_entry.py 面向打包模式：直接引用 app 对象，避免 frozen 环境下的字符串导入问题。
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="WhaleJu 本地引擎（打包版）")
    ap.add_argument("--port", type=int, default=7420)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--log-level", default="warning")
    args = ap.parse_args()

    # PyInstaller 下 __file__ 位于 _MEIPASS；engine.app 包已随包收集，
    # 父目录（_MEIPASS 根）需在 sys.path 上以 import engine.app.main。
    root = getattr(sys, "_MEIPASS", None)
    if root and root not in sys.path:
        sys.path.insert(0, root)

    import uvicorn
    from engine.app.main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return 0


if __name__ == "__main__":
    sys.exit(main())
