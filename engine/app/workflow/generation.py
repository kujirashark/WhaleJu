"""生成批次管理：设计 §6.4 的 start/pause/progress 三端点后端。
职责边界：
- 引擎是唯一事实源：12 个镜头的 queued/running/done/failed 全部在此推进。
- 前端只渲染 progress 返回值，不做任何业务判断。
- 纯开源版不设平台额度：只用你自己的厂商账号，用量只记本地事件。
- 去演示化：每个镜头真实调用已配置 Provider 的 submit→poll；异步视频按
  poll 返回的 pending 状态真实轮询（有上限），不再模拟失败、不再伪造进度。
"""
from __future__ import annotations
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any
from ..adapters.base import GenResult
from ..adapters.base import ImageGenRequest, VideoGenRequest
from ..adapters.registry import ProviderRegistry
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
    asset_id: str | None = None     # 本机素材 id：界面拿它读缩略图/视频，永久有效
    ability: str = "image"          # 这一镜用哪种能力生成（image=画面 / video=视频）
    idx: int = 0                    # 分镜表里的序号（展示用，与 shot_id 解耦）
    importance: str = "transition"  # key=重要镜头 / transition=过渡镜头
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
    # 致命原因：厂商根本不支持这个能力（如把图片模型填进视频槽）。
    # 一旦出现就立刻停批，不把 12 个镜头逐个撞一遍墙。
    fatal_reason: str | None = None
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
        ability = self.items[0].ability if self.items else "image"
        unit = price_for(ability)
        return {
            "batch_id": self.id,
            **c,
            "paused": self.paused,
            "eta_s": eta,
            "fatal_reason": self.fatal_reason,
            "ability": ability,
            "unit_price": unit,
            "estimated_cost": round(unit * c["total"], 2),
            "failed_items": [
                {"shot_id": i.shot_id, "scene_desc": i.scene_desc,
                 "fail_reason": i.fail_reason, "auto_retry_left": i.auto_retry_left}
                for i in self.items if i.status == "failed"
            ],
            "items": [
                {"shot_id": i.shot_id, "scene_desc": i.scene_desc,
                 "status": i.status, "cost": i.cost,
                 "asset_ref": i.asset_ref, "asset_id": i.asset_id,
                 "ability": i.ability, "fail_reason": i.fail_reason}
                for i in self.items
            ],
        }
SCENES = [
    "院子里 · 童年跑过", "晾衣绳 · 空镜", "站台 · 少年回头", "绿皮车 · 窗边",
    "写字楼 · 深夜加班", "街边 · 一碗面", "医院 · 走廊长椅", "病房 · 光",
    "老屋 · 门廊", "公园 · 长椅", "夕阳 · 大远景", "背影 · 定格",
]
PRICE_PER_SHOT = 9.0            # 视频镜头（平台代采口径）
PRICE_PER_IMAGE = 1.5           # 画面（平台代采口径）：图片比视频便宜得多
POLL_INTERVAL_S = 1.5       # 异步视频厂商轮询间隔
POLL_MAX_ROUNDS = 120       # 单镜头最多轮询轮数（约 3 分钟），超时按失败退回冻结
def price_for(ability: str) -> float:
    return PRICE_PER_IMAGE if ability == "image" else PRICE_PER_SHOT
def db_shot_id(project_id: str, shot_id: str) -> str:
    """镜头在数据库里的唯一标识。
    历史坑：曾经直接把 "s1" 这种短 ID 当 shots.id（全局主键），
    于是项目 A 的第 1 镜会覆盖项目 B 的第 1 镜，
    assets.shot_id 外键也跟着串到别的项目上 —— 换镜头重生成会拿错素材。
    现在统一带上项目 ID。
    """
    if not project_id or shot_id.startswith(f"{project_id}_"):
        return shot_id
    return f"{project_id}_{shot_id}"
def _is_capability_error(reason: str) -> bool:
    """判断错误是不是"厂商根本不支持这个能力"（而不是偶发失败）。
    典型场景：把图片模型填进「生成视频」槽，厂商返回 404/405，
    重试多少次都不会成功 —— 必须立刻停下来并说清楚。
    """
    r = (reason or "").lower()
    return any(k in r for k in (
        "http 404", "http 405", "http 501", "not found", "method not allowed",
        "unsupported", "no_provider_configured",
    ))
class GenerationManager:
    def __init__(self, db: Database, registry: ProviderRegistry, assets=None):
        self.db = db
        self.registry = registry
        # 素材落地仓库：厂商链接会过期，产物必须取回本机
        self.assets = assets
        self.batches: dict[str, Batch] = {}
        self.by_project: dict[str, str] = {}
    def current(self, project_id: str) -> Batch | None:
        bid = self.by_project.get(project_id)
        return self.batches.get(bid) if bid else None
    async def start(self, project_id: str, shot_count: int = 12,
                    ability: str = "image") -> Batch:
        existing = self.current(project_id)
        if existing and not existing.finished_at:
            return existing
        batch = Batch(id=ulid(), project_id=project_id, total=shot_count)
        scenes = self._scenes_from_project(project_id, shot_count)
        # shot_id 用镜头的稳定 key（不是序号）：用户重排/删除镜头后，
        # 素材关联依然指向"这一镜"，不会串到别的镜头上去。
        batch.items = [
            ShotProgress(
                shot_id=sc["key"], scene_desc=sc["scene"], ability=ability,
                idx=sc.get("idx") or (i + 1), importance=sc.get("importance") or "transition",
            )
            for i, sc in enumerate(scenes[:shot_count])
        ]
        self._sync_shot_rows(project_id, batch.items)
        self.batches[batch.id] = batch
        self.by_project[project_id] = batch.id
        batch.task = asyncio.create_task(self._run(batch), name=f"batch-{batch.id}")
        return batch
    def _sync_shot_rows(self, project_id: str, items: list[ShotProgress]) -> None:
        """把这一批镜头写进 shots 表。
        为什么要写：assets.shot_id 有外键指向 shots(id)，不写就存不下
        "这张画面属于哪个镜头"，而"只重生成这一个镜头"必须靠这个关联。
        镜头 ID 必须带项目前缀（db_shot_id）：shots.id 是全局主键，
        用 "s1" 会让不同项目的第 1 镜互相覆盖，素材外键也跟着串台。
        """
        try:
            eps = self.db.list(
                "SELECT id FROM episodes WHERE project_id=? ORDER BY idx LIMIT 1", (project_id,)
            )
            if not eps:
                return
            ep_id = eps[0]["id"]
            for it in items:
                self.db.execute(
                    """INSERT INTO shots(id,episode_id,idx,scene_desc,prompt,importance,ability,source,status)
                       VALUES(?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET scene_desc=excluded.scene_desc,
                                                   prompt=excluded.prompt,
                                                   idx=excluded.idx,
                                                   importance=excluded.importance,
                                                   ability=excluded.ability""",
                    (db_shot_id(project_id, it.shot_id), ep_id, it.idx or 0,
                     it.scene_desc, it.scene_desc, it.importance, it.ability, "owned", "planned"),
                )
        except Exception:  # noqa: BLE001 - shots 表写不进去不该阻断生成
            pass
    async def regenerate_shot(self, project_id: str, shot_id: str,
                              ability: str | None = None) -> dict[str, Any]:
        """只重跑这一个镜头（其它镜头不动）。
        用户要的是"这一张不满意，重新出一张"，不是整批 12 张重跑一遍。
        """
        batch = self.current(project_id)
        if not batch:
            raise RuntimeError("这个项目还没有生成批次，先说「生成画面」")
        idx = next((i for i, it in enumerate(batch.items) if it.shot_id == shot_id), None)
        if idx is None:
            raise RuntimeError(f"找不到镜头 {shot_id}")
        item = batch.items[idx]
        # 用用户在第 5 步改过的最新描述：编辑了分镜却重生成旧画面，是最让人抓狂的 bug
        latest = self._shot_scene_from_plan(project_id, item.shot_id)
        if latest:
            item.scene_desc = latest
        # 旧画面作废：否则导出时新旧两张都会被拼进去
        self._drop_shot_assets(project_id, shot_id, idx)
        item.status = "queued"
        item.fail_reason = None
        item.asset_ref = None
        item.asset_id = None
        item.cost = 0.0
        if ability:
            item.ability = ability
        ok = await self._run_shot(batch, idx, item)
        return {
            "ok": ok,
            "shot_id": shot_id,
            "status": item.status,
            "asset_id": item.asset_id,
            "fail_reason": item.fail_reason,
            "cost": item.cost,
        }
    def _drop_shot_assets(self, project_id: str, shot_id: str, index: int | None = None) -> None:
        """删掉这个镜头之前生成的素材（记录 + 本机文件）。
        老数据没写 assets.shot_id（没有精确关联），就按生成顺序取对应那一张，
        否则重生成后新旧两张都在，导出会多出一段重复画面。
        """
        db_id = db_shot_id(project_id, shot_id)
        try:
            rows = self.db.list(
                "SELECT id, local_path FROM assets WHERE project_id=? AND shot_id=?", (project_id, db_id)
            )
            if not rows:
                # 也可能是历史遗留的裸 shot_id（"s1"）
                rows = self.db.list(
                    "SELECT id, local_path FROM assets WHERE project_id=? AND shot_id=?", (project_id, shot_id)
                )
            if not rows and index is not None:
                legacy = self.db.list(
                    "SELECT id, local_path FROM assets WHERE project_id=? "
                    "AND kind IN ('shot','video') ORDER BY created_at",
                    (project_id,),
                )
                if index < len(legacy):
                    rows = [legacy[index]]
        except Exception:  # noqa: BLE001
            return
        for r in rows:
            try:
                p = self.assets.resolve(r["local_path"]) if self.assets else None
                if p and p.exists() and p.is_file():
                    p.unlink()
            except OSError:
                pass
            try:
                self.db.execute("DELETE FROM assets WHERE id=?", (r["id"],))
            except Exception:  # noqa: BLE001
                pass
    def _scenes_from_project(self, project_id: str, shot_count: int) -> list[dict]:
        """镜头描述必须来自用户第 5 步确认的真实分镜表。
        过去这里用的是写死的示例场景，导致生成的画面和用户看到的镜头表对不上，
        画面里出现的是程序自己编的场景。
        现在用户可以单独编辑分镜（见 /api/projects/{pid}/shots 的编辑端点），
        所以这里读的是**编辑后的最新**分镜表。
        """
        scenes: list[dict] = []
        try:
            row = self.db.get("projects", project_id) or {}
        except Exception:  # noqa: BLE001
            row = {}
        raw = row.get("shots_json")
        if raw:
            try:
                data = json.loads(raw)
                for i, s in enumerate((data.get("shots") or [])[:shot_count]):
                    desc = str(s.get("scene") or "").strip()
                    if not desc:
                        continue
                    scenes.append({
                        # 老数据没有 key：退回序号形式（素材关联走 legacy 兜底）
                        "key": str(s.get("key") or f"s{i + 1}"),
                        "scene": desc,
                        "importance": s.get("importance") if s.get("importance") in ("key", "transition") else "transition",
                        "idx": int(s.get("idx") or (i + 1)),
                    })
            except (ValueError, TypeError, AttributeError):
                scenes = []
        while len(scenes) < shot_count:
            n = len(scenes)
            scenes.append({
                "key": f"s{n + 1}",
                "scene": SCENES[n % len(SCENES)],
                "importance": "transition",
                "idx": n + 1,
            })
        return scenes
    def _shot_scene_from_plan(self, project_id: str, shot_id: str) -> str:
        """从分镜表里取某一镜的**最新**描述。
        单镜重生成时必须用用户改过的描述，否则"编辑了分镜但重生成还是旧画面"。
        """
        try:
            row = self.db.get("projects", project_id) or {}
            raw = row.get("shots_json")
            if not raw:
                return ""
            data = json.loads(raw)
            for i, s in enumerate(data.get("shots") or []):
                key = str(s.get("key") or f"s{i + 1}")
                if key == shot_id:
                    return str(s.get("scene") or "")
        except (ValueError, TypeError, AttributeError):
            return ""
        return ""
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
    async def _prompt_for(self, project_id: str, scene_desc: str) -> str:
        """组装生成提示词：镜头场景 + 已确认角色的外貌锚点（保持人物一致）。"""
        anchors: list[str] = []
        try:
            rows = self.db.list(
                "SELECT name, desc_text FROM characters WHERE project_id=? ORDER BY id", (project_id,)
            )
            for r in rows[:5]:
                desc = str(r.get("desc_text") or "").strip()
                if desc:
                    anchors.append(desc)
        except Exception:  # noqa: BLE001 - 锚点取不到不阻断生成
            anchors = []
        if not anchors:
            return f"{scene_desc}。竖屏构图，写实电影感，画面干净。"
        return (
            f"{scene_desc}。竖屏构图，写实电影感，画面干净。\n"
            "人物设定（必须与定妆图保持一致）：\n" + "\n".join(f"- {a}" for a in anchors)
        )
    async def _run_shot(self, batch: Batch, idx: int, item: ShotProgress) -> bool:
        """真实生成一个镜头。
        能力口径：
        - 第 6 步「生成画面」用 image 能力（图片模型），这与界面语义一致，
          也让只配了文字+图片模型的用户能把流程走完；
        - 若项目已有视频素材能力（配了视频模型），可以按 video 能力生成视频镜头。
        计费口径（纯开源版）：
        - 不存在平台额度概念，全部走你自己的厂商账号；
        - 这里只在本地 usage_events 记一条用量与成本估算，供「用量统计」查看。
        """
        item.status = "running"
        ability = item.ability or "image"
        route = self.registry.route(ability, "key" if idx % 2 == 0 else "transition")
        if not route:
            item.status = "failed"
            item.fail_reason = f"no_provider_configured:{ability}"
            batch.fatal_reason = (
                f"还没有配置{'图片' if ability == 'image' else '视频'}模型，"
                "请到「设置」里填好并点「测试连接」通过后再生成。"
            )
            return False
        provider = self.registry.get(route.provider_id)
        if provider is None:
            item.status = "failed"
            item.fail_reason = "provider_missing"
            return False
        unit_price = price_for(ability)
        try:
            prompt = await self._prompt_for(batch.project_id, item.scene_desc)
            if ability == "image":
                task_id = await provider.submit(
                    ImageGenRequest(prompt=prompt, size="1024x1536")
                )
            else:
                task_id = await provider.submit(
                    VideoGenRequest(prompt=prompt, duration_s=5, ratio="9:16")
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
            item.cost = result.raw_cost_estimate or unit_price
            item.status = "done"
            item.asset_ref = result.asset_ref
            self.db.insert("usage_events", {
                "id": ulid(), "ts": utc_now(), "project_id": batch.project_id,
                "provider_id": route.provider_id, "source": route.source,
                "ability": ability, "units": 1.0 if ability == "image" else 5.0,
                # 纯开源版没有平台积分，credits_spent 恒为 0，只留成本估算
                "credits_spent": 0.0,
                "raw_cost_estimate": item.cost, "ok": 1,
            })
            # 素材落库：批次只存在于内存，刷新页面后第 7 步会看不到任何画面。
            # 这里把真实产物登记进 assets，项目详情就能按项目读回真实素材。
            if item.asset_ref:
                self._register_asset(batch.project_id, item)
            return True
        except Exception as exc:  # noqa: BLE001 - Provider 异常统一走失败/重试
            reason = str(exc)[:60] or "provider_error"
            # 厂商根本不支持这个能力（端点不存在 / 方法不允许）：
            # 立刻停批并说清楚原因，别把 12 个镜头逐个撞一遍墙还只给一句"失败"。
            if _is_capability_error(reason):
                item.status = "failed"
                item.fail_reason = reason
                item.auto_retry_left = 0
                batch.fatal_reason = (
                    f"厂商不支持这个能力：{reason}。"
                    "请检查「设置」里这一项填的模型是否真的支持该能力"
                    "（例如图片模型不能用来生成视频）。"
                )
                return False
            if item.auto_retry_left > 0:
                item.auto_retry_left -= 1
                item.fail_reason = f"retryable: {reason}"
                item.status = "queued"
                return False  # 由 _run 决定是否重试（真实换源）
            item.status = "failed"
            item.fail_reason = reason
            return False
    def _register_asset(self, project_id: str, item: ShotProgress) -> str:
        """把生成的画面/视频取回本机并登记 assets 表。
        厂商给的是带签名、会过期的链接；不落地的话项目过一晚全是裂图。
        下载失败不阻塞生成（链接仍可临时查看），但会如实记录。
        返回本机素材 id：界面靠它读缩略图/视频，永久有效。
        """
        remote = item.asset_ref or ""
        looks_video = remote.lower().split("?")[0].endswith((".mp4", ".mov", ".webm"))
        # kind 区分素材用途：character=定妆图（第 3 步），shot=镜头画面（第 7 步看成片）
        kind = "video" if looks_video else "shot"
        asset_id = ""
        if self.assets is not None and remote:
            # shot_id 一起登记：这样"只重生成这一个镜头"能精确找到旧素材。
            # 用带项目前缀的库内 ID（db_shot_id），与 shots 表主键保持一致。
            asset = self.assets.save_remote(
                project_id, kind, remote, shot_id=db_shot_id(project_id, item.shot_id),
            )
            if asset:
                asset_id = asset["id"]
        if not asset_id:
            # 落地失败：登记一条指向原厂链接的行，界面还能临时看
            try:
                asset_id = ulid()
                self.db.insert("assets", {
                    "id": asset_id, "project_id": project_id, "kind": kind,
                    "local_path": remote, "sha256": "pending", "size_bytes": 0,
                })
            except Exception:  # noqa: BLE001 - 登记失败不影响已完成的生成
                pass
        item.asset_id = asset_id or None
        return asset_id
    async def _run(self, batch: Batch) -> None:
        """逐镜头真实推进。每次重试切换候选 Provider，不用同一家重复撞墙。"""
        try:
            for idx, item in enumerate(batch.items):
                if batch.fatal_reason:
                    # 致命原因已出现：剩下的镜头直接标记为未执行，不再消耗额度
                    item.status = "failed"
                    item.fail_reason = "skipped: " + (batch.fatal_reason or "")
                    continue
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
