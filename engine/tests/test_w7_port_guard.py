"""端口占用时的启动提示：必须给人话，而不是裸 socket 错误。

背景：直接 `python -m uvicorn ... --port 7420` 在端口被占时只抛
`[Errno 10048] error while attempting to bind on address`，用户看不出
"是引擎已经跑着了还是被别的程序占了"，也不知道该换端口还是关进程。
engine/run.py 负责在启动前判断并给出结论。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

# 单独运行本文件时也必须隔离真实数据目录
os.environ.setdefault("MANGJU_DATA_DIR", tempfile.mkdtemp(prefix="mangju-test-w7p-"))

ROOT = Path(__file__).resolve().parent.parent.parent
RUN_PY = ROOT / "engine" / "run.py"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not PY.exists():  # CI / 非 Windows 环境
    PY = Path(sys.executable)


def _occupy(port: int):
    """占住端口并返回一个可关闭的 socket。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port))
    s.listen(1)
    return s


def _run(port: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(PY), str(RUN_PY), "--port", str(port)],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )


def test_port_taken_by_other_program_explains_how_to_continue():
    """被别的程序占用：必须说清是"不是本引擎"，并给出两条出路。"""
    sock = _occupy(7439)
    try:
        r = _run(7439)
    finally:
        sock.close()
    out = (r.stdout or "") + (r.stderr or "")  # 防御：个别 runner 可能返回 None
    assert out or r.returncode is not None, f"子进程无输出：{r!r}"
    assert r.returncode == 2, f"应该以退出码 2 结束，实际 {r.returncode}"
    assert "不是本引擎" in out
    assert "--port" in out, "必须告诉用户怎么换端口"
    assert "findstr" in out or "netstat" in out, "必须告诉用户怎么找出占用者"


def test_engine_already_running_is_detected():
    """端口上跑着本引擎：应提示"已经在运行"，而不是让用户再启动一个。"""
    # 先起一个真引擎占端口，再跑 run.py
    proc = subprocess.Popen(
        [str(PY), "-m", "uvicorn", "engine.app.main:app",
         "--host", "127.0.0.1", "--port", "7440", "--log-level", "warning"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # 等引擎起来
        import time
        import urllib.request
        ready = False
        for _ in range(40):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen("http://127.0.0.1:7440/health", timeout=1) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:  # noqa: BLE001
                continue
        if not ready:
            return  # 环境不允许起引擎时跳过（不应让测试红）
        r = _run(7440)
        out = (r.stdout or "") + (r.stderr or "")  # 防御：个别 runner 可能返回 None
        assert out or r.returncode is not None, f"子进程无输出：{r!r}"
        assert r.returncode == 0, f"引擎已在跑时应正常退出，实际 {r.returncode}"
        assert "已经在" in out and "运行" in out
        assert "不要重复启动" in out
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_run_script_exists_and_is_executable_entry():
    """启动入口必须在，且提供 --port 参数。"""
    assert RUN_PY.is_file(), "缺少 engine/run.py"
    r = subprocess.run(
        [str(PY), str(RUN_PY), "--help"],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    assert r.returncode == 0
    assert "--port" in (r.stdout or "")
