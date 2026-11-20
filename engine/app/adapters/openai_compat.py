"""OpenAI 兼容适配器：自带 Key 直连厂商（BYOM，零平台接触）。
用于文本槽（DeepSeek/Qwen/OpenAI 等）。视频槽的可灵适配器结构相同，
仅 endpoint 与请求体不同；本期先交付文本槽真实链路。
"""
from __future__ import annotations
import asyncio
import time
import httpx
from .base import (
    GenResult, ImageGenRequest, ProbeResult, ProviderMeta,
    SpeechRequest, TextGenRequest, VideoGenRequest,
)
class OpenAICompatProvider:
    def __init__(self, provider_id: str, endpoint: str, api_key: str, model: str = "deepseek-chat"):
        self.meta = ProviderMeta(
            id=provider_id, kind="openai_compat", source="owned",
            abilities=("text",), unit_price_hint=0.001,
        )
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._results: dict[str, GenResult] = {}
    async def probe(self) -> ProbeResult:
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(
                    f"{self.endpoint}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            ok = r.status_code == 200
            return ProbeResult(
                ok=ok,
                latency_ms=int((time.monotonic() - t0) * 1000),
                abilities=("text",) if ok else (),
                price_hint="按厂商公开单价",
                error=None if ok else f"HTTP {r.status_code}",
            )
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(ok=False, error=str(exc))
    async def submit(self, req: object) -> str:
        if not isinstance(req, TextGenRequest):
            raise ValueError("OpenAICompatProvider 仅支持 text 槽")
        task_id = f"oc_{int(time.time() * 1000)}_{hash(req.prompt) & 0xFFFFFFF:x}"
        try:
            async with httpx.AsyncClient(timeout=60.0) as c:
                r = await c.post(
                    f"{self.endpoint}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": req.system},
                            {"role": "user", "content": req.prompt},
                        ],
                        "max_tokens": req.max_tokens,
                        "temperature": req.temperature,
                    },
                )
            if r.status_code != 200:
                self._results[task_id] = GenResult(ok=False, fail_reason="provider_error")
                return task_id
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            self._results[task_id] = GenResult(
                ok=True, asset_ref=f"text://{task_id}",
                units_used=data.get("usage", {}).get("total_tokens", 0) / 1000,
                raw_cost_estimate=0.0,
            )
            # 内容存内存供 poll 返回（W1 简化；W2 落 assets 表）
            self._results[task_id].provider_task_id = content[:2000]
        except Exception:  # noqa: BLE001
            self._results[task_id] = GenResult(ok=False, fail_reason="timeout")
        return task_id
    async def poll(self, task_id: str) -> GenResult:
        await asyncio.sleep(0)
        return self._results.get(task_id, GenResult(ok=False, fail_reason="unknown"))
