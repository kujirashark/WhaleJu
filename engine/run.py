"""引擎启动入口：端口被占用时给人话提示，而不是裸 socket 错误。
直接 `python -m uvicorn engine.app.main:app --port 7420` 在端口已被占用时，
uvicorn 只会抛一句：
    ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 7420)
用户看不出"是引擎已经跑着了，还是被别的程序占了"，也不知道该怎么办。
这里在启动前先判断端口状态，给出对应结论和可直接执行的下一步。
用法：
    .venv/Scripts/python.exe engine/run.py            # 默认 7420
    .venv/Scripts/python.exe engine/run.py --port 7421
"""
from __future__ import annotations
import argparse
import socket
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 7420
def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """端口是否已被监听。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0
def engine_alive(port: int, host: str = "127.0.0.1") -> bool:
    """占用端口的是不是我们自己的引擎（健康检查）。"""
    import json
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=1.5) as r:
            if r.status != 200:
                return False
            data = json.loads(r.read().decode("utf-8"))
            return bool(data.get("ok"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return False
def main() -> int:
    ap = argparse.ArgumentParser(description="启动鲸鲨漫剧本地引擎")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"监听端口（默认 {DEFAULT_PORT}）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--log-level", default="info")
    args = ap.parse_args()
    if port_in_use(args.port, args.host):
        if engine_alive(args.port, args.host):
            print(f"引擎已经在 {args.host}:{args.port} 上运行了。")
            print(f"直接访问 http://{args.host}:{args.port} 即可，不要重复启动。")
            print("如果想换端口重跑：python engine/run.py --port 7421")
            return 0
        print(f"端口 {args.port} 被别的程序占用了（不是本引擎）。")
        print("两种办法：")
        print(f"  1) 换个端口启动：python engine/run.py --port {args.port + 1}")
        print(f"  2) 找出占用者并关掉它：netstat -ano | findstr :{args.port}")
        return 2
    import uvicorn
    # 用字符串形式的 app 引用时，uvicorn 会自己 import "engine.app.main"，
    # 必须在 sys.path 上能找到项目根（从别处调用本脚本时最容易踩这个坑）。
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    print(f"引擎启动中：http://{args.host}:{args.port}")
    uvicorn.run(
        "engine.app.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )
    return 0
if __name__ == "__main__":
    sys.exit(main())
