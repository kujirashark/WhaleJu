"""配置驱动的通用 HTTP Provider（真实 API 接入层）。
设计约束（2026-11-20 去演示化）：
- 生产路径不再注册任何 Mock；所有能力由用户在设置页配置 endpoint + key + model 后真实调用。
- 每个 Provider 实例由 model_configs 一行配置构造：source / provider_kind / endpoint / credential / model。
- 四类能力统一走 OpenAI 兼容 HTTP 协议；视频支持异步两段式（submit 返回 task_id，poll 取结果）。
- 网络失败、非 200、字段缺失一律返回 GenResult(ok=False)，绝不伪造成功结果。
- 凭证只在内存中使用，调用完不落日志、不写入 GenResult。
厂商适配说明：MiniMax / 可灵 / DeepSeek / Ollama / ComfyUI 只要暴露 OpenAI 兼容接口，
填对应 endpoint + model 即可；不兼容的厂商新增一个薄适配器即可，业务层零改动。
"""
from __future__ import annotations
import asyncio
import time
import httpx
from .base import (
    GenResult, ImageGenRequest, ProbeResult, ProviderMeta,
    SpeechRequest, TextGenRequest, VideoGenRequest,
)
class ConfiguredProvider:
    """由设置页配置构造的真实 HTTP Provider。"""
    def __init__(
        self,
        provider_id: str,
        source: str,                    # owned / local / proxy
        abilities: tuple[str, ...],
        endpoint: str,
        api_key: str = "",
        model: str = "",
        provider_kind: str = "openai_compat",
        timeout: float = 60.0,
    ) -> None:
        self.meta = ProviderMeta(
            id=provider_id, kind=provider_kind, source=source,
            abilities=abilities, unit_price_hint=0.0,
        )
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._results: dict[str, GenResult] = {}
        self._assets: dict[str, str] = {}    # task_id -> 远端素材 URL / 本地落地路径
    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h
    # 限流/临时故障时重试：SenseNova 等免费额度常返回 429 tpm/rpm，
    # 不重试会让用户每次生成都失败，误以为软件跑不通。
    RETRY_STATUS = {408, 429, 500, 502, 503, 504}
    RETRY_DELAY_S = (1.0, 2.0, 4.0)  # 三次退避，总计约 7 秒
    def _post(self, path: str, payload: dict) -> tuple[int, dict | None, str]:
        """同步底层 POST（在 async 方法内用 asyncio.to_thread 调用，避免阻塞事件循环）。
        对限流/临时故障做指数退避重试，重试耗尽才如实返回失败。"""
        import time as _time
        last_status, last_err = 0, ""
        for attempt in range(len(self.RETRY_DELAY_S) + 1):
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.post(self.endpoint + path, headers=self._headers(), json=payload)
                if r.status_code == 200:
                    return 200, r.json(), ""
                last_status, last_err = r.status_code, f"HTTP {r.status_code}: {r.text[:120]}"
                if r.status_code not in self.RETRY_STATUS:
                    return last_status, None, last_err  # 4xx 非限流：立刻失败，不重试
            except Exception as exc:  # noqa: BLE001
                last_status, last_err = 0, str(exc)[:160]
            if attempt < len(self.RETRY_DELAY_S):
                _time.sleep(self.RETRY_DELAY_S[attempt])
        return last_status, None, last_err
    async def stream_chat(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ):
        """OpenAI 兼容流式对话：逐块 yield 文本增量。
        厂商返回 `data: {"choices":[{"delta":{"content":"..."}}]}` 的 SSE 行，
        以 `data: [DONE]` 结束。任何失败都通过 RuntimeError 抛出，交由上层
        如实反馈，绝不伪造 token。
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system or "你是短剧编剧，输出简洁的中文剧本。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        import json as _json
        for attempt in range(len(self.RETRY_DELAY_S) + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    async with c.stream("POST", self.endpoint + "/chat/completions",
                                        headers=self._headers(), json=payload) as r:
                        if r.status_code != 200:
                            body = (await r.aread()).decode("utf-8", "replace")[:160]
                            if r.status_code in self.RETRY_STATUS and attempt < len(self.RETRY_DELAY_S):
                                import asyncio as _aio
                                await _aio.sleep(self.RETRY_DELAY_S[attempt])
                                continue
                            raise RuntimeError(f"HTTP {r.status_code}: {body}")
                        async for line in r.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                return
                            try:
                                obj = _json.loads(data)
                                delta = obj["choices"][0].get("delta", {}).get("content")
                            except (ValueError, KeyError, IndexError, TypeError):
                                continue
                            if delta:
                                yield delta
                        return
            except RuntimeError:
                raise
            except Exception as exc:  # noqa: BLE001
                if attempt < len(self.RETRY_DELAY_S):
                    import asyncio as _aio
                    await _aio.sleep(self.RETRY_DELAY_S[attempt])
                    continue
                raise RuntimeError(f"流式连接失败：{str(exc)[:120]}") from exc
    async def probe(self) -> ProbeResult:
        """真实探测：GET {endpoint}/models，成功即视为可用。不返回任何 mock 结果。"""
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(self.endpoint + "/models", headers=self._headers())
            ok = r.status_code == 200
            models: list[str] = []
            if ok:
                try:
                    data = r.json()
                    models = [m.get("id", "") for m in data.get("data", [])][:10]
                except Exception:  # noqa: BLE001
                    pass
            return ProbeResult(
                ok=ok,
                latency_ms=int((time.monotonic() - t0) * 1000),
                abilities=self.meta.abilities if ok else (),
                price_hint=f"已连接 · {len(models)} 个模型" if ok else "",
                error=None if ok else f"HTTP {r.status_code} · {r.text[:80]}",
            )
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(ok=False, error=f"连接失败：{str(exc)[:120]}")
    async def submit(self, req: object) -> str:
        """提交生成任务。同步能力（text/image/speech）在 submit 内完成（伪异步）；
        视频按厂商能力提交异步任务，返回 provider task_id 供 poll。"""
        task_id = f"cfg_{int(time.time() * 1000)}_{hash(repr(req)) & 0xFFFFFFF:x}"
        if isinstance(req, TextGenRequest):
            status, data, err = await asyncio.to_thread(self._post, "/chat/completions", {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": req.system or "你是短剧编剧，输出简洁的中文剧本。"},
                    {"role": "user", "content": req.prompt},
                ],
                "max_tokens": req.max_tokens,
                "temperature": req.temperature,
            })
            if status != 200 or not data:
                self._results[task_id] = GenResult(ok=False, fail_reason=f"provider_error: {err}")
                return task_id
            try:
                content = data["choices"][0]["message"]["content"]
                units = data.get("usage", {}).get("total_tokens", 0) / 1000
                self._results[task_id] = GenResult(
                    ok=True, asset_ref=f"text://{task_id}", units_used=units,
                    raw_cost_estimate=0.0, provider_task_id=content,
                )
            except (KeyError, IndexError, TypeError) as exc:
                self._results[task_id] = GenResult(ok=False, fail_reason=f"bad_response: {exc}")
            return task_id
        if isinstance(req, ImageGenRequest):
            status, data, err = await asyncio.to_thread(self._post, "/images/generations", {
                "model": self.model,
                "prompt": req.prompt,
                "n": 1,
                "size": req.size,
                "response_format": "url",
            })
            if status != 200 or not data:
                self._results[task_id] = GenResult(ok=False, fail_reason=f"provider_error: {err}")
                return task_id
            try:
                url = data["data"][0]["url"]
                self._results[task_id] = GenResult(ok=True, units_used=1.0)
                self._assets[task_id] = url
            except (KeyError, IndexError, TypeError) as exc:
                self._results[task_id] = GenResult(ok=False, fail_reason=f"bad_response: {exc}")
            return task_id
        if isinstance(req, VideoGenRequest):
            status, data, err = await asyncio.to_thread(self._post, "/video/generations", {
                "model": self.model,
                "prompt": req.prompt,
                "duration": req.duration_s,
                "resolution": req.ratio,
            })
            if status != 200 or not data:
                self._results[task_id] = GenResult(ok=False, fail_reason=f"provider_error: {err}")
                return task_id
            provider_tid = str(data.get("id") or data.get("task_id") or data.get("task") or "")
            if not provider_tid:
                self._results[task_id] = GenResult(ok=False, fail_reason="bad_response: no task id")
                return task_id
            self._results[task_id] = GenResult(ok=True, provider_task_id=provider_tid)
            self._assets[task_id] = provider_tid
            return task_id
        if isinstance(req, SpeechRequest):
            status, data, err = await asyncio.to_thread(self._post, "/audio/speech", {
                "model": self.model, "input": req.text, "voice": req.voice_id, "speed": req.speed,
            })
            if status != 200 or not data:
                self._results[task_id] = GenResult(ok=False, fail_reason=f"provider_error: {err}")
                return task_id
            self._results[task_id] = GenResult(ok=True, units_used=1.0)
            return task_id
        self._results[task_id] = GenResult(ok=False, fail_reason="unsupported_request")
        return task_id
    async def poll(self, task_id: str) -> GenResult:
        """查询结果。视频走真实轮询 GET {endpoint}/video/generations/{id}；
        同步能力直接返回 submit 阶段写好的结果。"""
        result = self._results.get(task_id)
        if not result:
            return GenResult(ok=False, fail_reason="unknown_task")
        if not result.provider_task_id or result.provider_task_id.startswith("text://"):
            return result
        # 异步任务（视频）：真实查询厂商状态
        remote_id = self._assets.get(task_id, "")
        if not remote_id:
            return result
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.get(
                    self.endpoint + f"/video/generations/{remote_id}",
                    headers=self._headers(),
                )
            if r.status_code != 200:
                return GenResult(ok=False, fail_reason=f"poll_http_{r.status_code}")
            data = r.json()
            status = str(data.get("status", "")).lower()
            if status in ("succeeded", "success", "completed", "done"):
                url = str(data.get("video_url") or data.get("url") or data.get("file") or "")
                if not url:
                    return GenResult(ok=False, fail_reason="no_asset_url")
                result.asset_ref = url
                result.ok = True
                self._assets[task_id] = url
                return result
            if status in ("failed", "error", "cancelled"):
                result.ok = False
                result.fail_reason = f"provider_{status}"
                return result
            # 仍在处理中
            result.ok = False
            result.fail_reason = "pending"
            return result
        except Exception as exc:  # noqa: BLE001
            return GenResult(ok=False, fail_reason=f"poll_error: {str(exc)[:80]}")
