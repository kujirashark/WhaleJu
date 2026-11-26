"""Provider 协议与统一结果信封（设计 v3.1 §5.2）。

关键设计：文本/生图在 submit 内完成（伪异步），上层只面对 submit→poll 两段式。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class TextGenRequest:
    prompt: str
    system: str = ""
    max_tokens: int = 2048
    temperature: float = 0.7


@dataclass
class ImageGenRequest:
    prompt: str
    ref_image_asset: str | None = None
    size: str = "1024x1536"


@dataclass
class VideoGenRequest:
    prompt: str
    first_frame_asset: str | None = None
    duration_s: int = 5
    ratio: str = "9:16"


@dataclass
class SpeechRequest:
    text: str
    voice_id: str = "default"
    speed: float = 1.0


@dataclass
class GenResult:
    ok: bool
    asset_ref: str | None = None
    units_used: float = 0.0
    raw_cost_estimate: float = 0.0
    fail_reason: str | None = None
    provider_task_id: str | None = None


@dataclass
class ProviderMeta:
    id: str
    kind: str                       # openai_compat / kling / jimeng / helo / ollama / comfyui / mock
    source: str                     # proxy / owned / local
    abilities: tuple[str, ...] = ("text", "image", "video", "speech")
    unit_price_hint: float = 0.0


@dataclass
class ProbeResult:
    ok: bool
    latency_ms: int = 0
    abilities: tuple[str, ...] = ()
    price_hint: str = ""
    error: str | None = None
    models: tuple[str, ...] = ()   # 厂商返回的可用模型标识（用于校验用户填的模型名对不对）
    warning: str | None = None     # 连接成功但配置可能用错（如把图片模型填进视频槽）


class Provider(Protocol):
    meta: ProviderMeta

    async def probe(self) -> ProbeResult: ...
    async def submit(self, req: object) -> str: ...
    async def poll(self, task_id: str) -> GenResult: ...
