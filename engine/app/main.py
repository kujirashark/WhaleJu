"""鲸鲨漫剧本地引擎 FastAPI 入口（127.0.0.1:7420）。"""
from __future__ import annotations
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from .adapters.base import VideoGenRequest
from .adapters.registry import ProviderRegistry
from .adapters.loader import load_configured_providers
from .billing.ledger import CreditLedger, InsufficientCredits
from .storage.db import Database
from .storage.assets import AssetStore
from .storage.util import dumps, loads, ulid, utc_now
from .storage.vault import decrypt, encrypt, mask
from .adapters.configured_provider import ConfiguredProvider
from .adapters import call_log
from .workflow.state_machine import GuardError, WorkflowEngine
from .workflow.checkpoints import CheckpointManager
from .workflow.generation import GenerationManager, PRICE_PER_IMAGE, PRICE_PER_SHOT
from .workflow.content import ContentGenerator, NoProviderError
from .workflow.episode_spec import parse_episode_count
from .agent.agent import ConversationAgent, Intent
from .publish.kit import PublishKit
DATA_DIR = Path(os.getenv("MANGJU_DATA_DIR", str(Path.cwd() / "engine" / "data")))
DB = Database(DATA_DIR / "mangju.db")
LEDGER = CreditLedger(DB)
WORKFLOW = WorkflowEngine()
CHECKPOINTS = CheckpointManager(DB)
AGENT = ConversationAgent()
REGISTRY = ProviderRegistry()
PUBLISH = PublishKit(DATA_DIR)
ASSETS = AssetStore(DB, DATA_DIR)
GENERATIONS = GenerationManager(DB, LEDGER, REGISTRY, ASSETS)
CONTENT = ContentGenerator(DB, REGISTRY, ASSETS)
def refresh_providers() -> list[str]:
    """从本机配置重建真实 Provider 注册表（无任何配置时为空）。"""
    return load_configured_providers(DB, REGISTRY)
def ensure_providers(ability: str) -> bool:
    """生成前自愈：注册表缺该能力时，从数据库重新加载已验证配置。
    背景：Provider 注册表是内存态，只在 lifespan 启动时与保存/测试配置时刷新。
    用户在设置页测通某个能力、或引擎进程比配置更旧时，当前进程内存里仍是旧的
    （空）注册表，生成就会误报 E4001。这里在每次生成前按需重建，杜绝误报。
    """
    if REGISTRY.has_ability(ability):
        return True
    refresh_providers()
    return REGISTRY.has_ability(ability)
def advance_status(pid: str, event: str, ctx: dict | None = None, skip: bool = False) -> str | None:
    """把项目推过业务状态机的下一个节点，并落库到 projects.status。
    业务闭环的关键：状态机原本只有 steps/{step}/advance 端点会调用，
    而前端从不调用它 —— 结果 status 永远停在 DRAFT，首页进度、检查点、
    恢复逻辑全是死的。这里让每个真实业务动作顺手推进自己的节点，
    保证「做到哪一步」与引擎状态永远一致。
    """
    p = DB.get("projects", pid)
    if not p:
        return None
    try:
        nxt, _effects = WORKFLOW.advance(p["status"], event, ctx or {}, skip=skip)
    except GuardError:
        return None
    DB.execute("UPDATE projects SET status=? WHERE id=?", (nxt, pid))
    return nxt
def sync_status(pid: str, p: dict, role_count: int = 0) -> str:
    """状态自愈：库里已有真实产物、但 status 还停在早期节点时（例如旧版本生成的数据），
    自动对齐到与产物一致的节点，避免用户点「确认」被守卫挡住、流程卡死。"""
    st = p.get("status") or "DRAFT"
    if st == "DRAFT" and p.get("script_json"):
        st = advance_status(pid, "script_ready") or st
    if st == "CHARACT" and role_count >= 1:
        st = advance_status(pid, "roles_ready",
                            {"role_count": role_count, "candidate_count": role_count}) or st
    return st
def _asset_url(local_path: str | None, asset_id: str | None, base: str = "") -> str | None:
    """素材可访问地址：厂商 URL 直接用；本机文件走引擎的只读文件端点。
    必须返回**绝对地址**：前端页面由 Vite/Tauri 提供，<img src="/api/...">
    会指向前端源站而不是引擎源站，结果就是一片裂图。所以这里带上引擎基址。
    """
    if not local_path:
        return None
    if local_path.startswith("http://") or local_path.startswith("https://"):
        return local_path
    if not asset_id:
        return None
    prefix = base.rstrip("/") if base else ""
    return f"{prefix}/api/assets/{asset_id}/file?token={LOCAL_TOKEN}"
# 本地鉴权 Token：优先使用桌面壳通过 IPC 注入的随机令牌；
# 独立运行时自动生成，重启轮换（防本机其他进程调用）。
# 任何情况下都不通过公开接口下发——Tauri 侧由 start_engine 直接返回。
LOCAL_TOKEN = os.getenv("MANGJU_LOCAL_TOKEN") or os.urandom(24).hex()
@asynccontextmanager
async def lifespan(app: FastAPI):
    DB.init_schema()
    refresh_providers()
    recovered = CHECKPOINTS.recover()
    if recovered:
        print(f"[recover] {len(recovered)} 个检查点挂起，等待用户确认（不自动推进）")
    _sync_episode_counts()
    yield
def _sync_episode_counts() -> None:
    """校准老项目的目标集数。
    老库里没有 episode_count 这一列（迁移后默认 1），而用户的想法里可能
    明确写了"三集"——这里按想法重新解析一次并写回，保证界面和生成提示词
    都按用户真正要的集数来，而不是一律当成 1 集或一律 3 集。
    """
    try:
        rows = DB.list("SELECT id, idea_text, episode_count FROM projects")
    except Exception as exc:  # noqa: BLE001
        print(f"[episode_count] 校准失败：{exc}")
        return
    for r in rows:
        want, _explicit = parse_episode_count(r.get("idea_text") or "")
        if want != (r.get("episode_count") or 0):
            try:
                DB.execute("UPDATE projects SET episode_count=? WHERE id=?", (want, r["id"]))
            except Exception as exc:  # noqa: BLE001
                print(f"[episode_count] 校准失败：{exc}")
                break
app = FastAPI(title="鲸鲨漫剧本地引擎", version="v1-w1", lifespan=lifespan)
# 桌面壳 WebView 的 Origin（仅这三类来源 + 本机绑定 + Token 鉴权，不开放公网）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://tauri.localhost",   # Tauri v2 Windows 正式来源
        "tauri://localhost",        # Tauri v2 macOS / Linux
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",  # 本地开发预览
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["X-Local-Token", "Content-Type"],
)
def auth(x_local_token: str | None = Header(default=None), token: str | None = None):
    """本地鉴权：优先 header；SSE(EventSource 无法自定义 header) 允许 query token。
    仅绑定 127.0.0.1，query token 不会出本机；生产桌面运行时令牌经 IPC 取得。
    """
    if (x_local_token or token) != LOCAL_TOKEN:
        raise HTTPException(401, "本地引擎鉴权失败")
class CreateProject(BaseModel):
    # min_length 不能按"字"卡：中文短标题是常态（"小鲸流浪记"只有 5 个字），
    # 之前按 10 字符校验会把正常输入直接挡在 422。
    idea: str = Field(min_length=2, max_length=2000)
    template_id: str = "life_3ep"
class AdvanceReq(BaseModel):
    action: str = Field(pattern="^(approve|reject|skip)$")
    payload: dict = Field(default_factory=dict)
class GenReq(BaseModel):
    prompt: str
    duration_s: int = 5
    ratio: str = "9:16"
    importance: str = "transition"
class RechargeReq(BaseModel):
    plan_id: str = Field(pattern="^(p1|p2|p3)$")
class SaveModelReq(BaseModel):
    source: str = Field(pattern="^(owned|local|proxy)$")
    provider_kind: str = Field(default="openai_compat", pattern="^(openai_compat|kling|jimeng|helo|ollama|comfyui)$")
    name: str = Field(min_length=1, max_length=60)
    endpoint: str = Field(min_length=8, max_length=500)   # 真实必填：所有来源都要有服务地址
    model: str = Field(min_length=1, max_length=120)      # 真实必填：模型标识
    credential: str | None = None                          # local 可为空；owned/proxy 需密钥
PLANS = {"p1": 50.0, "p2": 200.0, "p3": 1000.0}
SLOTS = ("text", "image", "video", "speech")
def _public_slot(slot: str) -> dict:
    with DB.read() as c:
        row = c.execute(
            "SELECT * FROM model_configs WHERE slot=? AND is_active=1", (slot,)
        ).fetchone()
    if not row:
        return {
            "source": None, "provider_kind": None, "name": None, "model": None,
            "endpoint": None, "status": "unset", "verified": False,
            "has_credential": False, "last_probe_at": None,
        }
    verified = bool(row["verified"])
    return {
        "source": row["source"], "provider_kind": row["provider_kind"],
        "name": row["name"], "model": row["model"], "endpoint": row["endpoint"],
        "status": "verified" if verified else "unverified",
        "verified": verified,
        # 只回传"是否存过密钥"，前端据此显示 ****，绝不回传明文或密文
        "has_credential": bool(row["credential_cipher"]),
        "last_probe_at": row["updated_at"],
    }
@app.get("/health")
def health():
    return {"ok": True, "service": "mangju-engine", "version": "v1-w1"}
@app.get("/api/local-token")
def local_token():
    """仅首次启动由 Tauri 通过 IPC 取走；生产环境应改为 IPC 通道而非 HTTP。"""
    return {"token": LOCAL_TOKEN}
@app.post("/api/projects", dependencies=[Depends(auth)])
def create_project(req: CreateProject):
    pid = ulid()
    # 集数从用户想法里解析：说了几集就几集，没说就 1 集（不写死 3）
    count, explicit = parse_episode_count(req.idea)
    DB.insert("projects", {
        "id": pid, "name": req.idea[:18], "template_id": req.template_id,
        "idea_text": req.idea, "status": "DRAFT", "episode_count": count,
    })
    for i in range(1, count + 1):
        DB.insert("episodes", {"id": ulid(), "project_id": pid, "idx": i, "status": "pending"})
    return {
        "id": pid, "name": req.idea[:18], "status": "DRAFT",
        "episode_count": count,
        "episode_count_explicit": explicit,
        "next_action": "draft_script",
    }
@app.get("/api/projects", dependencies=[Depends(auth)])
def list_projects():
    return {"items": DB.list("SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY updated_at DESC")}
@app.get("/api/projects/trash/list", dependencies=[Depends(auth)])
def list_trash():
    return {"items": DB.list("SELECT * FROM projects WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC")}
@app.delete("/api/projects/{pid}", dependencies=[Depends(auth)])
def delete_project(pid: str):
    """软删项目：列表不再显示，数据仍留在库里，可恢复（误删可救）。"""
    p = DB.get("projects", pid)
    if not p or p.get("deleted_at"):
        raise HTTPException(404, "项目不存在或已被清理")
    with DB.tx() as c:
        c.execute("UPDATE projects SET deleted_at=? WHERE id=?", (utc_now(), pid))
    return {"deleted": True, "id": pid}
@app.post("/api/projects/{pid}/restore", dependencies=[Depends(auth)])
def restore_project(pid: str):
    p = DB.get("projects", pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    with DB.tx() as c:
        c.execute("UPDATE projects SET deleted_at=NULL WHERE id=?", (pid,))
    return {"restored": True, "id": pid}
def _backfill_character_refs(pid: str, chars: list[dict]) -> None:
    """定妆图自愈落地：旧数据里存的是厂商临时链接（会过期），现场下载一份到本机。
    幂等：已落地（有 asset_id）的直接跳过；下载失败保留原链接，界面仍可显示。
    """
    for ch in chars:
        refs = loads(ch.get("ref_images"), [])
        if not refs:
            continue
        first = refs[0]
        if first.get("asset_id"):
            continue
        remote = first.get("remote_url") or first.get("url") or ""
        if not remote.startswith("http"):
            continue
        asset = ASSETS.save_remote(pid, "image", remote, character_id=ch["id"])
        if not asset:
            continue
        first["asset_id"] = asset["id"]
        first["url"] = asset["local_path"]
        first["remote_url"] = remote
        payload = dumps(refs)
        with DB.tx() as c:
            c.execute("UPDATE characters SET ref_images=? WHERE id=?", (payload, ch["id"]))
        # 同步内存态：否则调用方读到的还是旧的厂商链接
        ch["ref_images"] = payload
@app.get("/api/projects/{pid}", dependencies=[Depends(auth)])
def get_project(pid: str, request: Request):
    p = DB.get("projects", pid)
    if not p or p.get("deleted_at"):
        raise HTTPException(404, "项目不存在或已被清理")
    base = str(request.base_url)
    script = loads(p.get("script_json"), None) if p.get("script_json") else None
    shots = loads(p.get("shots_json"), None) if p.get("shots_json") else None
    chars = DB.list(
        "SELECT id,name,desc_text,ref_images,locked FROM characters WHERE project_id=? ORDER BY id",
        (pid,),
    )
    _backfill_character_refs(pid, chars)
    for ch in chars:
        refs = loads(ch.get("ref_images"), [])
        first = refs[0] if refs else {}
        # 定妆图已落地到本机 → 走引擎文件端点；没落地成功才退回厂商链接
        ch["ref_url"] = _asset_url(first.get("url"), first.get("asset_id"), base)
        ch["remote_url"] = first.get("remote_url")
    # 真实素材：第 7 步「看成片」必须读引擎里的真实产物，
    # 否则刷新页面后前端内存态清空，用户看到空白的第 7 步。
    assets = ASSETS.list_project(pid)
    for a in assets:
        a["url"] = _asset_url(a.get("local_path"), a.get("id"), base)
        # 归一化素材类型：老数据全是 image，用 character_id 区分定妆图与镜头画面
        if a.get("kind") == "image":
            a["kind"] = "character" if a.get("character_id") else "shot"
    status = sync_status(pid, p, len(chars))
    return {
        **p,
        "status": status,
        "script": script,
        "shots": shots,
        "characters": chars,
        "assets": assets,
        "resume_hint": f"当前状态：{p['status']}",
        "credits_frozen": LEDGER.wallet()["frozen"],
    }
class ScriptGenReq(BaseModel):
    version: int = Field(default=1, ge=1, le=99)
    # 只写第几集：留空=按项目目标集数整批写；给值=只写这一集（逐集推进，省 token）
    episode_index: int | None = Field(default=None, ge=1, le=99)
def _target_episode_count(p: dict) -> int:
    """项目目标集数（建项目时按用户想法解析的，不写死 3）。"""
    try:
        n = int(p.get("episode_count") or 1)
    except (TypeError, ValueError):
        n = 1
    return n if n > 0 else 1
def _episode_index_error(p: dict, episode_index: int | None) -> str | None:
    """要写的集超出目标集数时给出明确原因（空串=允许）。"""
    if not episode_index:
        return None
    total = _target_episode_count(p)
    if episode_index > total:
        return f"这个项目一共 {total} 集，不能写第 {episode_index} 集。"
    return None
@app.post("/api/projects/{pid}/script/generate", dependencies=[Depends(auth)])
async def generate_script(pid: str, req: ScriptGenReq = ScriptGenReq()):
    """用已配置的文本模型真实生成剧本；未配置则明确拒绝。"""
    p = DB.get("projects", pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    bad = _episode_index_error(p, req.episode_index)
    if bad:
        raise HTTPException(400, {"code": "E4005", "message": bad, "hint": "先改项目想法里的集数，或直接重新生成整稿"})
    ensure_providers("text")
    try:
        result = await CONTENT.generate_script(pid, p["idea_text"], req.version, req.episode_index)
        advance_status(pid, "script_ready")   # DRAFT → CP1_PENDING（等你确认剧本）
        return result
    except NoProviderError as exc:
        raw = str(exc)
        is_quota = "quota" in raw.lower() or "429" in raw or "rate" in raw.lower()
        message = "厂商额度或频率限制，暂时无法生成" if is_quota else raw
        hint = "等额度恢复或升级套餐；这不是模型配置问题" if is_quota else "到设置里配置文本模型并测试连接"
        raise HTTPException(400, {"code": exc.code, "message": message, "hint": hint})
@app.post("/api/projects/{pid}/script/generate/stream", dependencies=[Depends(auth)])
async def generate_script_stream(pid: str, req: ScriptGenReq = ScriptGenReq()):
    """流式生成剧本：SSE 推 token / done / error 三类事件。
    模型调用情况逐块可见；done 事件携带落库后的完整剧本；失败如实推 error。
    与对话 SSE 一致，token 由 fetch 读取（header 带令牌，不走 query）。
    """
    p = DB.get("projects", pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    ensure_providers("text")
    async def events():
        yield "event: stage\ndata: " + json.dumps({"text": "已连接文本模型，正在生成剧本（若厂商限流会自动重试，请稍候）…"}, ensure_ascii=False) + "\n\n"
        bad = _episode_index_error(p, req.episode_index)
        if bad:
            # 集数越界要说清楚，不能让界面只看到一个空流
            yield "event: error\ndata: " + json.dumps(
                {"message": bad, "hint": "先改项目想法里的集数，或直接重新生成整稿"}, ensure_ascii=False
            ) + "\n\n"
            return
        try:
            async for kind, value in CONTENT.stream_script(
                pid, p["idea_text"], req.version, req.episode_index
            ):
                if kind == "token":
                    yield "event: token\ndata: " + json.dumps({"t": value}, ensure_ascii=False) + "\n\n"
                elif kind == "call":
                    # 实时调用日志：请求地址、状态码、耗时、重试情况
                    yield "event: call\ndata: " + json.dumps(value, ensure_ascii=False) + "\n\n"
                elif kind == "wait":
                    # 限流退避：告诉用户"在等厂商恢复，还有几秒"
                    yield "event: wait\ndata: " + json.dumps(value, ensure_ascii=False) + "\n\n"
                else:
                    nxt = advance_status(pid, "script_ready")   # 剧本落库后同步推进到「等你确认剧本」
                    # 附上本次调用的量化结果，让用户看到这次到底生成了多少
                    meta = {
                        "chars": sum(len(ep.get("script") or "") for ep in (value.get("episodes") or [])),
                        "episodes": len(value.get("episodes") or []),
                        "title": value.get("title") or "",
                        # 模型这次没写完时如实告知：已保住写完的那几集
                        "partial": bool(value.get("partial")),
                        # 把最新业务状态一起推给前端：前端要靠它决定"下一步能不能点"
                        "project_status": nxt,
                    }
                    # meta 必须早于 done：前端收到 done 即结束读取
                    yield "event: meta\ndata: " + json.dumps(meta, ensure_ascii=False) + "\n\n"
                    yield "event: done\ndata: " + json.dumps(value, ensure_ascii=False) + "\n\n"
        except NoProviderError as exc:
            raw = str(exc)
            low = raw.lower()
            is_quota = "quota" in low or "429" in raw or "rate" in low
            is_truncated = exc.code == "E4004" or "没写完" in raw or "无法解析" in raw
            if is_quota:
                err = {
                    "code": exc.code,
                    "message": "厂商额度或频率限制，暂时无法生成",
                    "hint": "等额度恢复或升级套餐；这不是模型配置问题",
                }
            elif is_truncated:
                err = {
                    "code": exc.code or "E4004",
                    "message": raw,
                    "hint": "模型这次写到一半就断了 —— 点「重新生成」再试一次；"
                            "这不是模型配置有问题（连接测试是通过的）",
                }
            else:
                err = {
                    "code": exc.code,
                    "message": raw,
                    "hint": "到设置里检查文本模型",
                }
            yield "event: error\ndata: " + json.dumps(err, ensure_ascii=False) + "\n\n"
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
class CharactersGenReq(BaseModel):
    count: int = Field(default=5, ge=1, le=20)
@app.post("/api/projects/{pid}/characters/generate", dependencies=[Depends(auth)])
async def generate_characters(pid: str, request: Request, req: CharactersGenReq = CharactersGenReq()):
    """用已配置的图片模型真实生成定妆图；未配置则明确拒绝。"""
    p = DB.get("projects", pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    ensure_providers("image")
    try:
        chars = await CONTENT.generate_characters(pid, req.count)
        advance_status(pid, "roles_ready",
                       {"role_count": len(chars), "candidate_count": len(chars)})  # CHARACT → CP2_PENDING
        # 定妆图已落地本机 → 给出引擎可访问的绝对地址，界面直接就能显示
        base = str(request.base_url) if request is not None else ""
        for ch in chars:
            local = ch.get("ref_url") or ""
            if local and not local.startswith("http"):
                ch["ref_url"] = _asset_url(local, ch.get("asset_id"), base)
                ch["asset_id"] = ch.get("asset_id") or ""
        return {"items": chars}
    except NoProviderError as exc:
        raise HTTPException(400, {"code": exc.code, "message": str(exc), "hint": "到设置里配置图片模型并测试连接"})
class ShotsGenReq(BaseModel):
    shot_count: int = Field(default=12, ge=1, le=60)
@app.post("/api/projects/{pid}/shots/generate", dependencies=[Depends(auth)])
async def generate_shots(pid: str, req: ShotsGenReq = ShotsGenReq()):
    """用已配置的文本模型真实拆分镜头；未配置剧本时先生成剧本。"""
    p = DB.get("projects", pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    if not p.get("script_json"):
        raise HTTPException(409, {"code": "E4003", "message": "还没有剧本", "hint": "请先在第 1 步生成剧本"})
    ensure_providers("text")
    try:
        return await CONTENT.generate_shots(pid, req.shot_count)
    except NoProviderError as exc:
        raise HTTPException(400, {"code": exc.code, "message": str(exc), "hint": "到设置里配置文本模型并测试连接"})
@app.post("/api/projects/{pid}/steps/{step}/advance", dependencies=[Depends(auth)])
def advance(pid: str, step: int, req: AdvanceReq):
    p = DB.get("projects", pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    # 先自愈：库里产物已领先于 status 时（旧数据），先对齐再推进
    role_count = len(DB.list("SELECT id FROM characters WHERE project_id=?", (pid,)))
    p = dict(p)
    p["status"] = sync_status(pid, p, role_count)
    event_map = {1: "script_ready", 2: "approve", 4: "approve", 6: "all_done", 7: "approve", 8: "export_done"}
    event = "reject" if req.action == "reject" else event_map.get(step, "approve")
    ctx = dict(req.payload)
    if step == 6:
        ctx["budget_ok"] = True
    try:
        nxt, effects = WORKFLOW.advance(
            p["status"], event, ctx,
            skip=(req.action == "skip"),
        )
    except GuardError as e:
        raise HTTPException(400, {"code": e.code, "message": e.message})
    DB.execute("UPDATE projects SET status=? WHERE id=?", (nxt, pid))
    return {"project_status": nxt, "effects": list(effects)}
@app.post("/api/wallet/recharge", dependencies=[Depends(auth)])
def recharge(req: RechargeReq):
    amount = PLANS[req.plan_id]
    LEDGER.recharge(amount, ulid())
    return {"state": "synced", "balance": LEDGER.wallet()["balance"], "amount": amount}
class ChatReq(BaseModel):
    project_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)
class DecideReq(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    payload: dict = Field(default_factory=dict)
@app.post("/api/chat", dependencies=[Depends(auth)])
async def chat(req: ChatReq):
    """对话（JSON 版）：返回结构意图（intent），不执行写操作。"""
    intent = await AGENT.rewrite(req.message, req.project_id)
    return {"intent": intent.to_dict()}
@app.post("/api/chat/stream", dependencies=[Depends(auth)])
async def chat_stream(req: ChatReq):
    """对话（SSE 版，设计 §6.5）：token / intent / done 三事件。
    Never 层：只推 intent，绝不执行写操作；用户确认后由前端调业务接口。
    """
    intent = await AGENT.rewrite(req.message, req.project_id)
    async def events():
        # 问答类（如"你好""这剧讲啥"）没有可执行动作，不该弹确认条；
        # 给一句人话回答，并标记 needs_confirm=False，前端就不显示"确认执行"。
        needs_confirm = intent.op != "answer_question"
        if intent.op == "answer_question":
            reply = "我可以帮你写剧本、定妆图、拆镜头、生成画面或导出成片。直接说想做什么，例如「写三集剧本」。"
        else:
            reply = intent.confirm or "确认执行这一步吗？"
        for i in range(0, len(reply), 6):
            yield f"event: token\ndata: {json.dumps({'t': reply[i:i+6]}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.02)
        payload = intent.to_dict()
        payload["needs_confirm"] = needs_confirm
        yield f"event: intent\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json.dumps({'history_cursor': ulid()}, ensure_ascii=False)}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
@app.post("/api/agent/execute", dependencies=[Depends(auth)])
def agent_execute(intent: Intent):
    return AGENT.execute(intent)
@app.get("/api/checkpoints/recover", dependencies=[Depends(auth)])
def checkpoints_recover():
    return {"pending": CHECKPOINTS.recover()}
@app.get("/api/projects/{pid}/checkpoints", dependencies=[Depends(auth)])
def project_checkpoints(pid: str):
    return {"pending": CHECKPOINTS.pending_for(pid)}
@app.post("/api/checkpoints/{cp_id}/decide", dependencies=[Depends(auth)])
def checkpoint_decide(cp_id: str, req: DecideReq):
    try:
        snapshot = CHECKPOINTS.decide(cp_id, req.action == "approve", req.payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"decided": req.action, "resume_payload": snapshot}
class ExportReq(BaseModel):
    ratio: str = Field(pattern="^(9:16|16:9)$")
    with_subtitle: bool = True
    ai_badge: bool = True   # 服务端恒置 true，传 false 被忽略（Never 层）
    source_path: str | None = None  # W4：测试用本地素材路径；生产由镜头产物拼接
@app.post("/api/projects/{pid}/export", dependencies=[Depends(auth)])
async def export_project(pid: str, req: ExportReq, request: Request = None):
    p = DB.get("projects", pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    # 真实素材优先：优先用视频素材（模型生成的成片片段），
    # 没有视频就用第 6 步生成的画面序列合成一条动态漫成片。
    # 两者都没有 → 明确拒绝（409），绝不生成任何演示片。
    src = req.source_path
    result: dict | None = None
    # 同一项目复用同一个 work_id：反复点"重新导出"只更新同一件作品，
    # 不会再在作品库里堆出一堆几十 MB 的重复副本。
    existing = DB.list(
        "SELECT * FROM assets WHERE project_id=? AND kind='work' ORDER BY created_at DESC",
        (pid,),
    )
    work_id = existing[0]["id"] if existing else ""
    if src and Path(src).exists():
        result = await PUBLISH.compose(src, work_id=work_id or None, ai_badge=True)
    else:
        videos = [
            ASSETS.resolve(r["local_path"]) for r in DB.list(
                "SELECT local_path FROM assets WHERE project_id=? AND kind='video' ORDER BY created_at",
                (pid,),
            ) if ASSETS.resolve(r["local_path"]).exists()
        ]
        if videos:
            result = await PUBLISH.compose(videos[0], work_id=work_id or None, ai_badge=True)
        else:
            frames = [
                ASSETS.resolve(r["local_path"]) for r in DB.list(
                    "SELECT local_path FROM assets WHERE project_id=? "
                    "AND (kind='shot' OR (kind='image' AND character_id IS NULL)) "
                    "ORDER BY created_at",
                    (pid,),
                ) if ASSETS.resolve(r["local_path"]).exists()
            ]
            if not frames:
                raise HTTPException(409, {
                    "code": "E4002", "message": "还没有真实画面可以导出",
                    "hint": "请先完成第 6 步生成真实画面。没有素材时不会生成演示片。",
                })
            try:
                result = await PUBLISH.compose_slides(
                    frames, work_id=work_id or None,
                    seconds_per_image=2.0, ratio=req.ratio or "9:16",
                )
            except RuntimeError as exc:
                # 没有 ffmpeg 时不硬堵死：把画面素材包导出到作品库，
                # 用户装了 ffmpeg 后可以自行合成，成果不会丢。
                result = PUBLISH.export_frames(
                    frames, project_id=pid,
                    project_name=p.get("name") or "未命名项目",
                    work_id=work_id or None,
                )
                result["needs_ffmpeg"] = True
                result["reason"] = str(exc)[:120]
    # 库里统一存相对数据目录的路径（绝对路径会随迁移失效）
    rel_path = ASSETS.rel_path(result["local_path"])
    row = {
        "id": result["work_id"], "project_id": pid, "kind": "work",
        "local_path": rel_path, "sha256": "pending",
        "size_bytes": result["size_bytes"],
    }
    if existing:
        DB.execute(
            "UPDATE assets SET local_path=?, size_bytes=? WHERE id=?",
            (rel_path, result["size_bytes"], result["work_id"]),
        )
    else:
        DB.insert("assets", row)
    DB.execute("UPDATE projects SET status='DELIVER' WHERE id=?", (pid,))
    out = dict(result)
    out["local_path"] = rel_path
    out["download_url"] = f"/api/works/{result['work_id']}/download?token={LOCAL_TOKEN}"
    out["format"] = result.get("format") or ("frames" if result.get("needs_ffmpeg") else "mp4")
    return out
@app.get("/api/calls", dependencies=[Depends(auth)])
def list_calls(limit: int = 60):
    """最近的模型调用记录：让模型调用不再是黑盒。"""
    return {"items": call_log.recent(limit)}
@app.get("/api/assets/{asset_id}/file")
def asset_file(asset_id: str, token: str | None = None):
    """素材只读文件端点：第 3/7 步要用 <img src> 展示真实画面，
    无法携带自定义请求头，因此这里用查询参数校验本地令牌。"""
    if token != LOCAL_TOKEN:
        raise HTTPException(401, "令牌无效")
    a = DB.get("assets", asset_id)
    if not a or not a.get("local_path"):
        raise HTTPException(404, "素材不存在")
    ref = a["local_path"]
    if ref.startswith("http://") or ref.startswith("https://"):
        raise HTTPException(409, "该素材是远端地址，请直接打开厂商链接")
    # 库里存的是相对数据目录的路径，必须按数据目录解析，
    # 直接 Path(ref) 会相对于进程工作目录，文件明明存在却报 404。
    p = ASSETS.resolve(ref)
    if not p.exists():
        raise HTTPException(404, "素材文件已被移动或删除")
    return FileResponse(p)
@app.get("/api/works", dependencies=[Depends(auth)])
def list_works():
    """作品库：带上项目名与集数，用户才认得出这是哪部剧的哪一集。"""
    items = DB.list("SELECT * FROM assets WHERE kind='work' ORDER BY created_at DESC")
    for it in items:
        p = DB.get("projects", it.get("project_id"))
        it["project_name"] = p["name"] if p else "未命名项目"
        # 真实产物形态：mp4 成片，还是没合成成功的画面素材包
        path = ASSETS.resolve(it.get("local_path") or "")
        is_dir = path.is_dir()
        it["format"] = "frames" if is_dir else "mp4"
        it["is_dir"] = is_dir
        it["frames"] = (
            len([f for f in path.iterdir()
                 if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")])
            if is_dir else 0
        )
        it["exists"] = path.exists()
        it["download_url"] = f"/api/works/{it['id']}/download?token={LOCAL_TOKEN}"
    return {"items": items}
@app.get("/api/works/{work_id}/download")
def download_work(work_id: str, token: str | None = None):
    """下载成片。
    <a download> 不能带自定义请求头，所以这里用查询参数校验本地令牌。
    """
    if token != LOCAL_TOKEN:
        raise HTTPException(401, "令牌无效")
    work = DB.get("assets", work_id)
    if not work or work["kind"] != "work":
        raise HTTPException(404, "作品不存在")
    path = ASSETS.resolve(work.get("local_path") or "")
    if not path.exists():
        raise HTTPException(404, "成片文件已被移动或删除，请重新导出")
    if path.is_dir():
        # 素材包：给一个 zip，下载体验和成片一致
        import zipfile
        zip_path = path.parent / f"{path.name}.zip"
        if not zip_path.exists():
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in path.iterdir():
                    if f.is_file():
                        zf.write(f, f.name)
        return FileResponse(zip_path, media_type="application/zip", filename=f"{path.name}.zip")
    return FileResponse(path, media_type="video/mp4", filename=path.name)
@app.get("/api/works/{work_id}/caption", dependencies=[Depends(auth)])
def work_caption(work_id: str, body: str = ""):
    work = DB.get("assets", work_id)
    if not work or work["kind"] != "work":
        raise HTTPException(404, "作品不存在")
    p = DB.get("projects", work["project_id"])
    name = p["name"] if p else "未命名项目"
    return {"caption": PUBLISH.caption(name, 1, body), "cached": False}
@app.get("/api/system/capabilities", dependencies=[Depends(auth)])
def system_capabilities():
    """本机能力自检：导出成片需要 ffmpeg，没有要提前告诉用户。"""
    from .publish.kit import _ffmpeg_path, _font_file
    ffmpeg = _ffmpeg_path()
    font = _font_file()
    return {
        "ffmpeg": bool(ffmpeg),
        "ffmpeg_path": ffmpeg,
        "font": bool(font),
        "hint": None if ffmpeg else (
            "本机没有可用的 ffmpeg：画面可以正常生成，但导出 mp4 需要它。"
            "装好后会自动识别；如果已安装，可在系统环境变量 WHALESHARK_FFMPEG 里指定 ffmpeg.exe 的完整路径。"
        ),
    }
@app.get("/api/wallet", dependencies=[Depends(auth)])
def wallet():
    return LEDGER.wallet()
@app.get("/api/model-configs", dependencies=[Depends(auth)])
def model_configs():
    return {"slots": {s: _public_slot(s) for s in SLOTS}}
@app.put("/api/model-configs/{slot}", dependencies=[Depends(auth)])
def save_model_config(slot: str, req: SaveModelReq):
    """保存真实 API 配置。凭证加密入库，此后任何接口不回显明文。
    保存后状态为 unverified——必须再点「测试连接」且真实探测通过，
    该槽位才可用于生成。杜绝"填了假地址也能跑"的演示行为。
    """
    if slot not in SLOTS:
        raise HTTPException(400, "未知能力槽")
    with DB.tx() as c:
        # 只改地址/模型、密钥留空时沿用原密文——否则用户改错地址后必须重填密钥才能保存。
        prev = c.execute(
            "SELECT * FROM model_configs WHERE slot=? AND is_active=1", (slot,)
        ).fetchone()
        has_prev_key = bool(prev and prev["credential_cipher"])
        if req.source in ("owned", "proxy") and not req.credential and not has_prev_key:
            raise HTTPException(400, "这个来源需要填写 API 密钥")
        cipher = encrypt(req.credential) if req.credential else (prev["credential_cipher"] if has_prev_key else None)
        # 配置实质未变（地址/模型/来源/密钥都相同）时，直接沿用原 verified，
        # 不再新建 unverified 行——否则用户仅重开设置页点保存，就把已测通的能力清成不可用。
        unchanged = bool(
            prev
            and prev["endpoint"] == req.endpoint
            and prev["model"] == req.model
            and prev["source"] == req.source
            and (not req.credential or cipher == prev["credential_cipher"])
        )
        if unchanged and prev["verified"]:
            c.execute(
                "UPDATE model_configs SET name=?, provider_kind=?, abilities=? WHERE id=?",
                (req.name, req.provider_kind, dumps([slot]), prev["id"]),
            )
        else:
            new_verified = 1 if unchanged else 0  # 未变则保留（含原本未验证），变了必须重测
            # 旧配置物理删除，不只是置 is_active=0：
            # 只置 0 的话每次保存都往表里堆一行（用户库里已积到 50+ 行），
            # 而界面上根本看不到它们，纯属垃圾数据。
            # 顺序要紧：先置 0，再删掉所有非激活行 —— 否则刚被置 0 的那行会留到下次。
            c.execute("UPDATE model_configs SET is_active=0 WHERE slot=?", (slot,))
            c.execute("DELETE FROM model_configs WHERE slot=? AND is_active=0", (slot,))
            c.execute(
                """INSERT INTO model_configs
                   (id,slot,source,provider_kind,name,endpoint,model,credential_cipher,abilities,verified,is_active)
                   VALUES(?,?,?,?,?,?,?,?,?,?,1)""",
                (ulid(), slot, req.source, req.provider_kind, req.name, req.endpoint,
                 req.model, cipher, dumps([slot]), new_verified),
            )
    refresh_providers()
    return {"saved": True, "slot": _public_slot(slot)}
@app.post("/api/model-configs/{slot}/test", dependencies=[Depends(auth)])
async def test_model_config(slot: str):
    """真实连接测试：GET {endpoint}/models。通过才置 verified=1 并允许生成。
    未配置 → 明确失败（引导用户先填地址），绝不返回 mock 可用。
    """
    if slot not in SLOTS:
        raise HTTPException(400, "未知能力槽")
    with DB.read() as c:
        row = c.execute(
            "SELECT * FROM model_configs WHERE slot=? AND is_active=1", (slot,)
        ).fetchone()
    # sqlite3.Row 没有 .get()：必须转成 dict，否则已配置时测试连接直接 500
    row = dict(row) if row else None
    if not row or not row.get("endpoint"):
        return {"ok": False, "verified": False, "error": "请先填写服务地址并保存", "mock": False}
    key = ""
    if row.get("credential_cipher"):
        try:
            key = decrypt(bytes(row["credential_cipher"]))
        except Exception:  # noqa: BLE001
            return {"ok": False, "verified": False, "error": "密钥无法解密，请重新填写", "mock": False}
    provider = ConfiguredProvider(
        provider_id=f"test_{slot}", source=row["source"], abilities=(slot,),
        endpoint=row["endpoint"], api_key=key, model=row.get("model") or "",
        provider_kind=row["provider_kind"], timeout=10.0,
    )
    result = await provider.probe()
    if result.ok:
        with DB.tx() as c:
            c.execute(
                "UPDATE model_configs SET verified=1, abilities=? WHERE id=?",
                (dumps(list(result.abilities) or [slot]), row["id"]),
            )
        refresh_providers()
    else:
        with DB.tx() as c:
            c.execute("UPDATE model_configs SET verified=0 WHERE id=?", (row["id"],))
        refresh_providers()
    error = result.error
    if not result.ok and error and "404" in error:
        error += "；服务地址应填到 /v1 为止（如 https://厂商域名/v1），不要带 /models 或 /chat/completions"
    return {"ok": result.ok, "verified": result.ok, "latency_ms": result.latency_ms,
            "abilities": list(result.abilities), "price_hint": result.price_hint,
            "error": error, "warning": result.warning, "mock": False,
            "models": list(result.models)[:20]}
@app.get("/api/capabilities", dependencies=[Depends(auth)])
def capabilities():
    """各能力槽的就绪状态，供前端在生成前明确提示未配置项。"""
    ready = {slot: _public_slot(slot)["verified"] for slot in SLOTS}
    return {
        "slots": {slot: _public_slot(slot) for slot in SLOTS},
        "ready": ready,
        "all_ready": all(ready.values()),
    }
class GenStartReq(BaseModel):
    shot_count: int = Field(default=12, ge=1, le=60)
    ability: str = Field(default="image", pattern="^(image|video)$")
@app.post("/api/projects/{pid}/generation/start", dependencies=[Depends(auth)])
async def generation_start(pid: str, req: GenStartReq = GenStartReq()):
    """设计 §6.4：开始生成批次。
    能力选择：第 6 步「生成画面」默认走 image 能力（图片模型），
    这与界面语义一致，也让只配了文字+图片模型的用户能把流程走完；
    显式指定 video 时才走视频模型。
    额度校验按来源区分：
    - 用自己的 API 密钥（owned）/ 本机模型（local）→ 不消耗平台额度，直接放行；
    - 用平台额度（proxy）→ 余额必须够跑完这批，否则明确拦下并给出出路。
    过去不分来源一律按平台额度拦，用自己密钥的用户会被假额度卡死。
    """
    p = DB.get("projects", pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    ability = req.ability or "image"
    # 前置校验：这一项能力必须已配置并通过真实连接测试，否则拒绝生成（无 Mock 兜底）
    ensure_providers(ability)
    if ability == "image" and not REGISTRY.has_ability("image"):
        # 降级：没有图片模型但有视频模型时，用视频模型出画面（流程照样能走完）
        ensure_providers("video")
        if REGISTRY.has_ability("video"):
            ability = "video"
        else:
            raise HTTPException(400, {
                "code": "E4001", "message": "还没有配置可用的图片模型",
                "hint": "请先到「设置 → 生成图片」填写服务地址和模型，并点「测试连接」通过后再开始",
            })
    if not REGISTRY.has_ability(ability):
        want = "图片" if ability == "image" else "视频"
        where = "生成图片" if ability == "image" else "生成视频"
        raise HTTPException(400, {
            "code": "E4001", "message": f"还没有配置可用的{want}模型",
            "hint": f"请先到「设置 → {where}」填写服务地址和模型，并点「测试连接」通过后再开始",
        })
    route = REGISTRY.route(ability, "key")
    uses_own_key = bool(route and route.source in ("owned", "local"))
    unit = PRICE_PER_IMAGE if ability == "image" else PRICE_PER_SHOT_ESTIMATE
    wallet = LEDGER.wallet()
    need = unit * req.shot_count
    if not uses_own_key and wallet["balance"] < need:
        raise HTTPException(400, {
            "code": "E2001",
            "message": f"平台额度不够跑完这批：需要 {need:g}，当前余额 {wallet['balance']:g}",
            "need": need,
            "balance": wallet["balance"],
            "hint": "两条路任选：顶栏「额度」充值后重试；或在「设置 → 生成视频」改成「用我自己的 API 密钥」，"
                    "用你自己的账号计费，不消耗平台额度",
        })
    batch = await GENERATIONS.start(pid, req.shot_count, ability=ability)
    advance_status(pid, "budget_confirmed",
                   {"available": wallet["balance"], "required": need})
    return {
        "batch_id": batch.id, "queued": req.shot_count,
        "ability": ability,
        "unit_price": unit,
        "estimated_cost": need,
        "route_reason": (
            "用你自己的 API 密钥生成，不消耗平台额度"
            if uses_own_key else
            f"用{'图片' if ability == 'image' else '视频'}模型逐个镜头生成，"
            f"每个镜头 {unit:g} 额度，失败不计费"
        ),
        "billing": "own_key" if uses_own_key else "platform_credits",
        "wallet": wallet,
    }
PRICE_PER_SHOT_ESTIMATE = PRICE_PER_SHOT
# PRICE_PER_IMAGE 从 workflow.generation 导入（唯一来源，避免两处价格不一致）
@app.post("/api/projects/{pid}/generation/pause", dependencies=[Depends(auth)])
async def generation_pause(pid: str):
    r = await GENERATIONS.pause(pid)
    if r is None:
        raise HTTPException(404, "没有进行中的生成批次")
    return {"paused": True, "done": r["done"], "total": r["total"]}
@app.post("/api/projects/{pid}/generation/resume", dependencies=[Depends(auth)])
async def generation_resume(pid: str):
    r = await GENERATIONS.resume(pid)
    if r is None:
        raise HTTPException(404, "没有可恢复的生成批次")
    return {"resumed": True, "done": r["done"], "total": r["total"]}
@app.get("/api/projects/{pid}/generation/progress", dependencies=[Depends(auth)])
async def generation_progress(pid: str):
    """进度是引擎事实；前端只渲染，不做业务判断。"""
    r = GENERATIONS.progress(pid)
    if r is None:
        # 尚未开始：这是一个真实的中性状态，不是伪装成"已排队 12 个"
        return {"batch_id": None, "done": 0, "total": 0, "running": 0, "failed": 0,
                "queued": 0, "paused": False, "eta_s": None,
                "failed_items": [], "items": [], "not_started": True}
    # 全部镜头完成 → RUNNING → CP3_PENDING（等你看成片确认）
    if r.get("total") and r.get("done", 0) >= r.get("total", 0) and not r.get("paused"):
        advance_status(pid, "all_done")
    return r
@app.post("/api/generation/submit", dependencies=[Depends(auth)])
async def generation_submit(req: GenReq):
    """单镜头真实生成（走已配置的 Provider；未配置则明确拒绝）。"""
    ensure_providers("video")
    route = REGISTRY.route("video", req.importance)
    if not route:
        raise HTTPException(400, {
            "code": "E4001", "message": "没有可用的视频模型",
            "hint": "请先到设置里配置视频模型并测试连接通过",
        })
    provider = REGISTRY.get(route.provider_id)
    # 自带密钥/本地模型来源不消耗平台额度（与批量生成同一口径）
    consumes_credits = route.source == "proxy"
    freeze_id = ""
    if consumes_credits:
        freeze_id = LEDGER.freeze(req.duration_s * 0.9, "smoke", route.provider_id, "video")
    try:
        tid = await provider.submit(VideoGenRequest(prompt=req.prompt, duration_s=req.duration_s, ratio=req.ratio))
        result = await provider.poll(tid)
    except Exception as exc:  # noqa: BLE001 - 边界：任何 Provider 异常都要退回冻结
        if freeze_id:
            LEDGER.settle(freeze_id, 0, False, "provider_error")
        raise HTTPException(502, f"生成失败：{exc}")
    if freeze_id:
        LEDGER.settle(freeze_id, result.raw_cost_estimate, result.ok, result.fail_reason)
    return {
        "task_id": tid, "ok": result.ok, "asset_ref": result.asset_ref,
        "route_reason": route.reason, "wallet": LEDGER.wallet(),
        "billing": "platform_credits" if consumes_credits else "own_key",
    }
