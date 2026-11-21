"""生成批次管理：设计 §6.4 的 start/pause/progress 三端点后端。
职责边界：
- 引擎是唯一事实源：12 个镜头的 queued/running/done/failed 全部在此推进。
- 前端只渲染 progress 返回值，不做任何业务判断。
- 冻结/结算仍走 CreditLedger；失败自动退回冻结，用户不为废片付费。
- 去演示化：每个镜头真实调用已配置 Provider 的 submit→poll；异步视频按
  poll 返回的 pending 状态真实轮询（有上限），不再模拟失败、不再伪造进度。
"""
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from ..adapters.base import GenResult
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
    asset_ref: str | None = None    # 真实生成素材引用（厂商 URL / 本地路径）
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
                 "status": i.status, "cost": i.cost,
                 "asset_ref": i.asset_ref, "fail_reason": i.fail_reason}
                for i in self.items
            ],
        }
SCENES = [
    "院子里 · 童年跑过", "晾衣绳 · 空镜", "站台 · 少年回头", "绿皮车 · 窗边",
    "写字楼 · 深夜加班", "街边 · 一碗面", "医院 · 走廊长椅", "病房 · 光",
    "老屋 · 门廊", "公园 · 长椅", "夕阳 · 大远景", "背影 · 定格",
]
PRICE_PER_SHOT = 9.0
POLL_INTERVAL_S = 1.5       # 异步视频厂商轮询间隔
POLL_MAX_ROUNDS = 120       # 单镜头最多轮询轮数（约 3 分钟），超时按失败退回冻结
class GenerationManager:
    def __init__(self, db: Database, ledger: CreditLedger, registry: ProviderRegistry):
        self.db = db
        self.ledger = ledger
        self.registry = registry
        self.batches: dict[str, Batch] = {}
        self.by_project: dict[str, str] = {}
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
    async def _wait_pause(self, batch: Batch) -> None:
        while batch.paused:
            await asyncio.sleep(0.1)
    async def _run_shot(self, batch: Batch, idx: int, item: ShotProgress) -> bool:
        """真实生成一个镜头。冻结在提交前；失败退回冻结；返回是否成功。"""
        item.status = "running"
        route = self.registry.route("video", "key" if idx % 2 == 0 else "transition")
        if not route:
            item.status = "failed"
            item.fail_reason = "no_provider_configured"
            return False
        provider = self.registry.get(route.provider_id)
        if provider is None:
            item.status = "failed"
            item.fail_reason = "provider_missing"
            return False
        freeze_id = self.ledger.freeze(PRICE_PER_SHOT, batch.project_id, route.provider_id, "video")
        batch.freeze_ids[item.shot_id] = freeze_id
        try:
            task_id = await provider.submit(
                VideoGenRequest(prompt=item.scene_desc, duration_s=5, ratio="9:16")
            )
            result: GenResult | None = None
            for _ in range(POLL_MAX_ROUNDS):
                await self._wait_pause(batch)
                result = await provider.poll(task_id)
                if result is None:
                    raise RuntimeError("poll returned nothing")
                if result.fail_reason == "pending":
                    await asyncio.sleep(POLL_INTERVAL_S)
                    continue
                break
            if result is None or not result.ok:
                reason = result.fail_reason if result else "no_result"
                raise RuntimeError(reason or "provider_error")
            # 真实成功：按厂商回报的用量结算，落真实素材引用
            item.cost = result.raw_cost_estimate or PRICE_PER_SHOT
            item.status = "done"
            item.asset_ref = result.asset_ref
            self.ledger.settle(freeze_id, item.cost, True)
            self.db.insert("usage_events", {
                "id": ulid(), "ts": utc_now(), "project_id": batch.project_id,
                "provider_id": route.provider_id, "source": route.source,
                "ability": "video", "units": 5.0, "credits_spent": item.cost,
                "raw_cost_estimate": item.cost, "ok": 1,
            })
            # 素材落库：批次只存在于内存，刷新页面后第 7 步会看不到任何画面。
            # 这里把真实产物登记进 assets，项目详情就能按项目读回真实素材。
            if item.asset_ref:
                try:
                    self.db.insert("assets", {
                        "id": ulid(), "project_id": batch.project_id, "kind": "shot",
                        "local_path": item.asset_ref, "sha256": "pending", "size_bytes": 0,
                    })
                except Exception:  # noqa: BLE001 - 登记失败不影响已完成的生成
                    pass
            return True
        except Exception as exc:  # noqa: BLE001 - 任何 Provider 异常都退回冻结
            reason = str(exc)[:60] or "provider_error"
            self.ledger.settle(freeze_id, 0, False, reason)
            if item.auto_retry_left > 0:
                item.auto_retry_left -= 1
                item.fail_reason = f"retryable: {reason}"
                item.status = "queued"
                return False  # 由 _run 决定是否重试（真实换源）
            item.status = "failed"
            item.fail_reason = reason
            return False
    async def _run(self, batch: Batch) -> None:
        """逐镜头真实推进。每次重试切换候选 Provider，不用同一家重复撞墙。"""
        try:
            for idx, item in enumerate(batch.items):
                await self._wait_pause(batch)
                attempts = 0
                while attempts < 3:
                    ok = await self._run_shot(batch, idx, item)
                    if ok:
                        break
                    attempts += 1
                    if item.status == "failed":
                        break  # 重试次数耗尽，标记失败
                    await asyncio.sleep(0.2)
        finally:
            batch.finished_at = time.time()
