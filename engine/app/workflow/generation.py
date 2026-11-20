"""生成批次管理：设计 §6.4 的 start/pause/progress 三端点后端。
职责边界：
- 引擎是唯一事实源：12 个镜头的 queued/running/done/failed 全部在此推进。
- 前端只渲染 progress 返回值，不做任何业务判断。
- 冻结/结算仍走 CreditLedger；失败自动退回冻结，用户不为废片付费。
- 当前视频槽为 MockProvider，任务按固定间隔推进；换真实适配器后只需替换
  `_run_shot` 内部调用，批次状态机不变。
"""
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from ..adapters.base import VideoGenRequest
from ..adapters.registry import ProviderRegistry
from ..billing.ledger import CreditLedger
from ..storage.db import Database
from ..storage.util import ulid, utc_now
@dataclass
class ShotProgress:
    shot_id: str
    scene_desc: str
    status: str = "queued"          # planned/queued/running/done/failed
    fail_reason: str | None = None
    auto_retry_left: int = 2
    cost: float = 0.0
@dataclass
class Batch:
    id: str
    project_id: str
    total: int
    items: list[ShotProgress] = field(default_factory=list)
    paused: bool = False
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    task: asyncio.Task | None = None
    freeze_ids: dict[str, str] = field(default_factory=dict)
    def counts(self) -> dict[str, int]:
        return {
            "done": sum(1 for i in self.items if i.status == "done"),
            "total": len(self.items),
            "running": sum(1 for i in self.items if i.status == "running"),
            "failed": sum(1 for i in self.items if i.status == "failed"),
            "queued": sum(1 for i in self.items if i.status == "queued"),
        }
    def to_progress(self) -> dict[str, Any]:
        c = self.counts()
        done = c["done"]
        elapsed = (self.finished_at or time.time()) - self.started_at
        eta = None
        if done and done < c["total"]:
            eta = max(1, round((elapsed / done) * (c["total"] - done)))
        return {
            "batch_id": self.id,
            **c,
            "paused": self.paused,
            "eta_s": eta,
            "failed_items": [
                {"shot_id": i.shot_id, "scene_desc": i.scene_desc,
                 "fail_reason": i.fail_reason, "auto_retry_left": i.auto_retry_left}
                for i in self.items if i.status == "failed"
            ],
            "items": [
                {"shot_id": i.shot_id, "scene_desc": i.scene_desc,
                 "status": i.status, "cost": i.cost}
                for i in self.items
            ],
        }
SCENES = [
    "院子里 · 童年跑过", "晾衣绳 · 空镜", "站台 · 少年回头", "绿皮车 · 窗边",
    "写字楼 · 深夜加班", "街边 · 一碗面", "医院 · 走廊长椅", "病房 · 光",
    "老屋 · 门廊", "公园 · 长椅", "夕阳 · 大远景", "背影 · 定格",
]
PRICE_PER_SHOT = 9.0
class GenerationManager:
    def __init__(self, db: Database, ledger: CreditLedger, registry: ProviderRegistry):
        self.db = db
        self.ledger = ledger
        self.registry = registry
        self.batches: dict[str, Batch] = {}
        self.by_project: dict[str, str] = {}
        self.tick_s = 0.35  # Mock 推进间隔；真实适配器由 poll 回调驱动
    def current(self, project_id: str) -> Batch | None:
        bid = self.by_project.get(project_id)
        return self.batches.get(bid) if bid else None
    async def start(self, project_id: str, shot_count: int = 12) -> Batch:
        existing = self.current(project_id)
        if existing and not existing.finished_at:
            return existing
        batch = Batch(id=ulid(), project_id=project_id, total=shot_count)
        batch.items = [
            ShotProgress(shot_id=f"s{i+1}", scene_desc=SCENES[i % len(SCENES)])
            for i in range(shot_count)
        ]
        self.batches[batch.id] = batch
        self.by_project[project_id] = batch.id
        batch.task = asyncio.create_task(self._run(batch), name=f"batch-{batch.id}")
        return batch
    async def pause(self, project_id: str) -> dict[str, Any] | None:
        batch = self.current(project_id)
        if not batch:
            return None
        # 已完成批次幂等返回（前端重复点击不应报 404）
        if batch.finished_at:
            r = batch.to_progress()
            r["already_finished"] = True
            return r
        batch.paused = True
        return batch.to_progress()
    async def resume(self, project_id: str) -> dict[str, Any] | None:
        batch = self.current(project_id)
        if not batch:
            return None
        if batch.finished_at:
            r = batch.to_progress()
            r["already_finished"] = True
            return r
        batch.paused = False
        return batch.to_progress()
    def progress(self, project_id: str) -> dict[str, Any] | None:
        batch = self.current(project_id)
        return batch.to_progress() if batch else None
    async def _run(self, batch: Batch) -> None:
        """逐镜头推进。冻结在提交前；失败退回冻结；第 5 镜头模拟一次失败换源。"""
        try:
            for idx, item in enumerate(batch.items):
                while batch.paused:
                    await asyncio.sleep(0.1)
                item.status = "running"
                route = self.registry.route("video", "key" if idx % 2 == 0 else "transition")
                if not route:
                    item.status = "failed"
                    item.fail_reason = "no_provider"
                    continue
                freeze_id = self.ledger.freeze(PRICE_PER_SHOT, batch.project_id, route.provider_id, "video")
                batch.freeze_ids[item.shot_id] = freeze_id
                # 真实适配器：submit → poll；Mock 下两者瞬时完成。
                # 第 5 镜头第一次 attempt 模拟 provider_error，自动换源重试不扣费。
                simulated_fail = idx == 4 and item.auto_retry_left == 2
                try:
                    if simulated_fail:
                        raise RuntimeError("mock provider timeout")
                    provider = self.registry.get(route.provider_id)
                    result = await provider.submit(
                        VideoGenRequest(prompt=item.scene_desc, duration_s=5, ratio="9:16")
                    )
                    poll = await provider.poll(result)
                    item.cost = poll.raw_cost_estimate
                    item.status = "done"
                    self.ledger.settle(freeze_id, item.cost, True)
                    self.db.insert("usage_events", {
                        "id": ulid(),
                        "ts": utc_now(),
                        "project_id": batch.project_id,
                        "provider_id": route.provider_id,
                        "source": route.source,
                        "ability": "video",
                        "units": 5.0,
                        "credits_spent": item.cost,
                        "raw_cost_estimate": item.cost,
                        "ok": 1,
                    })
                except Exception as exc:  # noqa: BLE001 - 任何 Provider 异常都退回冻结
                    self.ledger.settle(freeze_id, 0, False, "provider_error")
                    if item.auto_retry_left > 0:
                        item.auto_retry_left -= 1
                        item.fail_reason = f"provider_error: {str(exc)[:40]}"
                        # 换源重试：同镜头再跑一轮（不重复冻结）
                        item.status = "queued"
                        await asyncio.sleep(self.tick_s)
                        continue
                    item.status = "failed"
                    item.fail_reason = "provider_error"
                await asyncio.sleep(self.tick_s)
        finally:
            batch.finished_at = time.time()
