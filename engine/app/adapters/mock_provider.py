"""Mock Provider：无外部 API 也能跑通 W1 全链路（submit→poll→记账）。
真实适配器（helo_proxy / kling_direct）继承同样的 Provider 协议，
只把 submit/poll 换成厂商 HTTP 调用；业务层零改动。
"""
from __future__ import annotations
import asyncio
import hashlib
from .base import (
    GenResult, ImageGenRequest, ProbeResult, ProviderMeta,
    SpeechRequest, TextGenRequest, VideoGenRequest,
)
class MockProvider:
    def __init__(self, meta: ProviderMeta | None = None):
        self.meta = meta or ProviderMeta(
            # source=proxy：Mock 代表"平台代采"的可控替身，计费口径与平台代采一致
            # （自带密钥/本地模型不扣平台额度，见 workflow/generation.py）。
            # 生产路径不注册 Mock，这里只服务测试。
            id="mock", kind="mock", source="proxy",
            abilities=("text", "image", "video", "speech"),
        )
        self._tasks: dict[str, GenResult] = {}
    async def probe(self) -> ProbeResult:
        return ProbeResult(
            ok=True, latency_ms=12, abilities=self.meta.abilities,
            price_hint="模拟模式（不计费）",
        )
    async def submit(self, req: object) -> str:
        # 幂等：相同请求参数 → 相同 task_id（防崩溃恢复重复扣费）
        payload = repr(req).encode("utf-8")
        tid = "mt_" + hashlib.sha256(payload).hexdigest()[:20]
        if tid not in self._tasks:
            if isinstance(req, TextGenRequest):
                result = GenResult(ok=True, asset_ref=f"mock://text/{tid}", units_used=0.4)
            elif isinstance(req, ImageGenRequest):
                result = GenResult(ok=True, asset_ref=f"mock://image/{tid}", units_used=1.0, raw_cost_estimate=0.05)
            elif isinstance(req, VideoGenRequest):
                result = GenResult(ok=True, asset_ref=f"mock://video/{tid}", units_used=req.duration_s, raw_cost_estimate=req.duration_s * 0.9)
            elif isinstance(req, SpeechRequest):
                result = GenResult(ok=True, asset_ref=f"mock://speech/{tid}", units_used=1.0)
            else:
                result = GenResult(ok=False, fail_reason="unknown")
            self._tasks[tid] = result
        return tid
    async def poll(self, task_id: str) -> GenResult:
        await asyncio.sleep(0)  # 让出事件循环，模拟异步
        return self._tasks.get(task_id, GenResult(ok=False, fail_reason="unknown"))
