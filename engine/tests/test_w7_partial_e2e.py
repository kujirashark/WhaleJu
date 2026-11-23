"""端到端：模型输出被截断时的完整链路（引擎 SSE → 落库 → 标记 partial）。
用只吐半截 JSON 的假 Provider 触发，确认：
- SSE 的 meta 事件带 partial=true
- done 事件带回救后的集（不是空）
- 剧本确实落库
- 完全救不回来时，error 事件带 E4004 且提示不再误导用户去改模型配置
"""
from __future__ import annotations
import json
import os
import tempfile
# 单独运行本文件时也必须隔离：main.py 在 import 时固定 DATA_DIR
os.environ.setdefault("MANGJU_DATA_DIR", tempfile.mkdtemp(prefix="mangju-test-w7e-"))
from fastapi.testclient import TestClient
import pytest
from engine.app.main import app, DB, LOCAL_TOKEN, REGISTRY
from engine.app.adapters.base import ProviderMeta
HEADERS = {"X-Local-Token": LOCAL_TOKEN}
@pytest.fixture(autouse=True)
def clean_db():
    """与 test_w1 一致：每例前重建 schema 并清空数据（临时目录，不碰用户库）。"""
    DB.init_schema()
    with DB.tx() as c:
        for t in ("generation_tasks", "shots", "episodes", "checkpoints", "assets",
                  "usage_events", "characters", "projects", "model_configs"):
            c.execute(f"DELETE FROM {t}")
    REGISTRY.clear()
TRUNCATED = (
    '{"title":"被截断的剧","episodes":['
    '{"idx":1,"title":"第一集：开场","tags":["成长"],"script":"第一集完整写完了。"},'
    '{"idx":2,"title":"第二集：中断","script":"第二集正写到一半'
)
class _TruncatedTextProvider:
    """只吐截断内容的文本 Provider。"""
    def __init__(self, payload: str):
        self.meta = ProviderMeta(
            id="trunc_text", kind="openai_compat", source="proxy",
            abilities=("text",),
        )
        self._payload = payload
    async def probe(self):
        from engine.app.adapters.base import ProbeResult
        return ProbeResult(ok=True, latency_ms=1, abilities=("text",))
    async def stream_chat(self, prompt, system, max_tokens=2048):
        # 逐块吐出，模拟真实流式
        for i in range(0, len(self._payload), 40):
            yield ("delta", self._payload[i:i + 40])
        yield ("call", {"ts": "00:00:00", "ability": "text", "model": "trunc",
                        "endpoint": "http://x", "method": "POST", "path": "/chat/completions",
                        "status": 200, "ms": 1, "attempt": 1, "error": "", "note": "流式响应结束"})
def _sse_events(text: str):
    """把 SSE 响应文本解析成 [(event, data)]。"""
    out = []
    for block in text.split("\n\n"):
        ev = dt = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                dt = line[5:].strip()
        if ev and dt:
            try:
                out.append((ev, json.loads(dt)))
            except json.JSONDecodeError:
                out.append((ev, dt))
    return out
def test_truncated_script_stream_marks_partial_and_keeps_episodes():
    REGISTRY.register(_TruncatedTextProvider(TRUNCATED))
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "截断输出测试三集竖屏短剧"},
                      headers=HEADERS).json()["id"]
    with client.stream("POST", f"/api/projects/{pid}/script/generate/stream",
                       headers=HEADERS, json={"version": 1}) as r:
        text = "".join(r.iter_text())
    events = _sse_events(text)
    kinds = [e for e, _ in events]
    assert "error" not in kinds, f"截断不该整份失败：{text[:300]}"
    assert "done" in kinds
    meta = next(d for e, d in events if e == "meta")
    assert meta["partial"] is True, "meta 必须标记残缺"
    assert meta["episodes"] >= 1, "应该救回至少一集"
    done = next(d for e, d in events if e == "done")
    assert len(done["episodes"]) >= 1
    assert done["episodes"][0]["script"] == "第一集完整写完了。"
    assert done["partial"] is True
    # 确实落库了
    with DB.read() as c:
        row = c.execute("SELECT script_json FROM projects WHERE id=?", (pid,)).fetchone()
    stored = json.loads(row["script_json"])
    assert len(stored["episodes"]) >= 1
    assert stored["partial"] is True
def test_unrecoverable_truncation_gives_e4004_and_no_misleading_hint():
    REGISTRY.register(_TruncatedTextProvider("模型只说了句『我来写剧本了』然后就没了"))
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "完全截断测试三集竖屏短剧"},
                      headers=HEADERS).json()["id"]
    with client.stream("POST", f"/api/projects/{pid}/script/generate/stream",
                       headers=HEADERS, json={"version": 1}) as r:
        text = "".join(r.iter_text())
    events = _sse_events(text)
    err = next((d for e, d in events if e == "error"), None)
    assert err is not None, "救不回来必须报错，不能假装成功"
    assert err["code"] == "E4004"
    assert "没写完" in err["message"]
    # 关键：不能再把用户引去改模型配置（配置是好的，是模型这次没写完）
    assert "检查文本模型" not in err["hint"], f"提示不应误导用户改配置：{err['hint']}"
    assert "重新生成" in err["hint"]
    assert "没写完" in err["message"] or "中断" in err["message"]
