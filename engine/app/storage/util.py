"""通用工具：ULID 生成、时间、JSON 安全序列化。"""
from __future__ import annotations
import json
import secrets
import time
from datetime import datetime, timezone
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # 排除 I L O U
def ulid() -> str:
    """时间有序、26 位的 ULID（无第三方依赖）。"""
    ts = int(time.time() * 1000)
    out = []
    for _ in range(10):
        out.append(_CROCKFORD[ts % 32])
        ts //= 32
    prefix = "".join(reversed(out))
    suffix = "".join(_CROCKFORD[secrets.randbelow(32)] for _ in range(16))
    return prefix + suffix
def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
def loads(text: str | None, default=None):
    if not text:
        return default
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return default
