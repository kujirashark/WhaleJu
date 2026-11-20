"""从 model_configs 表加载用户真实配置 → 构造 Provider → 注册。
去演示化核心：只有 verified=1（真实连接测试通过）的槽位才注册；
没有任何配置时注册表为空，路由返回 None，前端收到明确错误「请先配置模型」。
绝不存在静默 Mock 兜底。
"""
from __future__ import annotations
from ..storage.db import Database
from ..storage.vault import decrypt
from .base import Provider
from .configured_provider import ConfiguredProvider
from .registry import ProviderRegistry
# 四个能力槽对应的实际 API 路径（OpenAI 兼容约定，厂商按此实现即可）
SLOT_ABILITIES = {
    "text": ("text",),
    "image": ("image",),
    "video": ("video",),
    "speech": ("speech",),
}
def load_configured_providers(db: Database, registry: ProviderRegistry) -> list[str]:
    """清掉非真实 provider，按已验证配置重建。返回已加载的 provider_id 列表。"""
    # 移除所有 ConfiguredProvider（保留测试中显式注册的其他 provider）
    for pid in list(registry._providers):
        if pid.startswith("cfg_"):
            registry.unregister(pid)
    loaded: list[str] = []
    rows = db.list(
        "SELECT * FROM model_configs WHERE is_active=1 AND verified=1 AND endpoint IS NOT NULL"
    )
    for row in rows:
        slot = row["slot"]
        if slot not in SLOT_ABILITIES:
            continue
        key = ""
        if row.get("credential_cipher"):
            try:
                key = decrypt(bytes(row["credential_cipher"]))
            except Exception:  # noqa: BLE001 - 密钥损坏按未配置处理，不伪造可用
                continue
        if not row.get("endpoint"):
            continue
        pid = f"cfg_{slot}"
        provider = ConfiguredProvider(
            provider_id=pid,
            source=row["source"],
            abilities=SLOT_ABILITIES[slot],
            endpoint=row["endpoint"],
            api_key=key,
            model=row.get("model") or "",
            provider_kind=row["provider_kind"],
        )
        registry.register(provider)
        loaded.append(pid)
    return loaded
