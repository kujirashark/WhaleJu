"""Provider 注册表：按能力槽 + 来源路由，可解释（reason 必填）。"""
from __future__ import annotations
from dataclasses import dataclass
from .base import Provider, ProviderMeta
@dataclass
class RouteDecision:
    provider_id: str
    source: str
    reason: str                     # UI 强制展示，禁止静默路由
    candidates: tuple[str, ...]     # 换源重试顺位
class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
    def register(self, provider: Provider) -> None:
        self._providers[provider.meta.id] = provider
    def unregister(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)
    def clear(self) -> None:
        self._providers.clear()
    def get(self, provider_id: str) -> Provider | None:
        return self._providers.get(provider_id)
    def has_ability(self, ability: str) -> bool:
        return any(ability in p.meta.abilities for p in self._providers.values())
    def all_meta(self) -> list[ProviderMeta]:
        return [p.meta for p in self._providers.values()]
    def route(
        self,
        ability: str,
        importance: str = "transition",
        prefer: str | None = None,
        active_slots: dict[str, str] | None = None,
    ) -> RouteDecision | None:
        """路由优先级：显式指定 > 镜头分级规则 > 能力/来源可用性。"""
        active_slots = active_slots or {}
        candidates = [
            p for p in self._providers.values()
            if ability in p.meta.abilities
        ]
        if prefer:
            candidates.sort(key=lambda p: (p.meta.id != prefer, _source_rank(p.meta.source)))
        elif ability == "video" and importance == "key":
            candidates.sort(key=lambda p: (_source_rank(p.meta.source), p.meta.id != "kling_direct"))
        else:
            candidates.sort(key=lambda p: (_source_rank(p.meta.source), p.meta.id))
        # active_slots 限制：若已配置来源，只保留该来源或 proxy（代采始终可用）
        allowed_source = active_slots.get(ability)
        if allowed_source:
            candidates = [p for p in candidates if p.meta.source in (allowed_source, "proxy")] or candidates
        if not candidates:
            return None
        top = candidates[0].meta
        reason = (
            f"{ability} 能力 → {top.kind}（{_source_label(top.source)}）"
            + ("；关键镜头优先自带模型" if ability == "video" and importance == "key" else "")
        )
        return RouteDecision(
            provider_id=top.id,
            source=top.source,
            reason=reason,
            candidates=tuple(p.meta.id for p in candidates[:3]),
        )
def _source_rank(source: str) -> int:
    return {"owned": 0, "local": 1, "proxy": 2, "mock": 9}.get(source, 9)
def _source_label(source: str) -> str:
    return {"owned": "自带密钥", "local": "本地模型", "proxy": "平台额度", "mock": "模拟"}.get(source, source)
