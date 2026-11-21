"""模型调用日志：记录每次真实 HTTP 调用，供界面实时展示。
设计目的：模型调用此前是黑盒——用户只看到最终文本，看不到请求发到哪、
返回什么状态、耗时多久、是否被限流重试。这里把每次调用如实记录下来，
失败也记录，不做美化。
线程安全：Provider 调用发生在 to_thread 工作线程中，读取发生在事件循环，
因此用锁保护。
"""
from __future__ import annotations
import threading
from collections import deque
from datetime import datetime
_MAX = 300
_log: deque[dict] = deque(maxlen=_MAX)
_lock = threading.Lock()
def record(
    ability: str,
    model: str,
    endpoint: str,
    method: str = "POST",
    path: str = "",
    status: int = 0,
    ms: int = 0,
    attempt: int = 1,
    error: str = "",
    note: str = "",
) -> dict:
    """登记一次模型调用并返回该条记录。"""
    entry = {
        "ts": datetime.now().strftime("%H:%M:%S"),
        "ability": ability,
        "model": model or "(未填模型)",
        "endpoint": endpoint or "",
        "method": method,
        "path": path,
        "status": status,
        "ms": ms,
        "attempt": attempt,
        "error": error[:200],
        "note": note,
    }
    with _lock:
        _log.append(entry)
    return entry
def recent(limit: int = 60) -> list[dict]:
    """返回最近的调用记录（最新在后）。"""
    with _lock:
        return list(_log)[-max(1, min(limit, _MAX)):]
def clear() -> None:
    with _lock:
        _log.clear()
