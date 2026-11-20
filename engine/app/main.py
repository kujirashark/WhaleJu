"""鲸鲨漫剧本地引擎 FastAPI 入口（127.0.0.1:7420）。"""
from __future__ import annotations
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from .adapters.base import VideoGenRequest
from .adapters.registry import ProviderRegistry
from .adapters.loader import load_configured_providers
from .billing.ledger import CreditLedger, InsufficientCredits
from .storage.db import Database
from .storage.util import dumps, loads, ulid, utc_now
from .storage.vault import decrypt, encrypt, mask
from .adapters.configured_provider import ConfiguredProvider
from .workflow.state_machine import GuardError, WorkflowEngine
from .workflow.checkpoints import CheckpointManager
from .workflow.generation import GenerationManager
from .workflow.content import ContentGenerator, NoProviderError
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
GENERATIONS = GenerationManager(DB, LEDGER, REGISTRY)
CONTENT = ContentGenerator(DB, REGISTRY)
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
    yield
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
    idea: str = Field(min_length=10, max_length=2000)
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
    DB.insert("projects", {
        "id": pid, "name": req.idea[:18], "template_id": req.template_id,
        "idea_text": req.idea, "status": "DRAFT",
    })
    for i in (1, 2, 3):
        DB.insert("episodes", {"id": ulid(), "project_id": pid, "idx": i, "status": "pending"})
    return {"id": pid, "name": req.idea[:18], "status": "DRAFT", "episode_count": 3, "next_action": "draft_script"}
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
@app.get("/api/projects/{pid}", dependencies=[Depends(auth)])
def get_project(pid: str):
    p = DB.get("projects", pid)
    if not p or p.get("deleted_at"):
        raise HTTPException(404, "项目不存在或已被清理")
    script = loads(p.get("script_json"), None) if p.get("script_json") else None
    shots = loads(p.get("shots_json"), None) if p.get("shots_json") else None
    chars = DB.list(
        "SELECT id,name,desc_text,ref_images,locked FROM characters WHERE project_id=? ORDER BY id",
        (pid,),
    )
    for ch in chars:
        refs = loads(ch.get("ref_images"), [])
        ch["ref_url"] = refs[0].get("url") if refs else None
    return {
        **p,
        "script": script,
        "shots": shots,
        "characters": chars,
        "resume_hint": f"当前状态：{p['status']}",
        "credits_frozen": LEDGER.wallet()["frozen"],
    }
class ScriptGenReq(BaseModel):
    version: int = Field(default=1, ge=1, le=99)
@app.post("/api/projects/{pid}/script/generate", dependencies=[Depends(auth)])
async def generate_script(pid: str, req: ScriptGenReq = ScriptGenReq()):
    """用已配置的文本模型真实生成剧本；未配置则明确拒绝。"""
    p = DB.get("projects", pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    ensure_providers("text")
    try:
        return await CONTENT.generate_script(pid, p["idea_text"], req.version)
    except NoProviderError as exc:
        raw = str(exc)
        is_quota = "quota" in raw.lower() or "429" in raw or "rate" in raw.lower()
        message = "厂商额度或频率限制，暂时无法生成" if is_quota else raw
        hint = "等额度恢复或升级套餐；这不是模型配置问题" if is_quota else "到设置里配置文本模型并测试连接"
        raise HTTPException(400, {"code": exc.code, "message": message, "hint": hint})
class CharactersGenReq(BaseModel):
    count: int = Field(default=5, ge=1, le=20)
@app.post("/api/projects/{pid}/characters/generate", dependencies=[Depends(auth)])
async def generate_characters(pid: str, req: CharactersGenReq = CharactersGenReq()):
    """用已配置的图片模型真实生成定妆图；未配置则明确拒绝。"""
    p = DB.get("projects", pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    ensure_providers("image")
    try:
        chars = await CONTENT.generate_characters(pid, req.count)
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
        # token 事件：白话逐字回显（规则模式下整段一句，生产由 LLM token 流替换）
        reply = intent.confirm or "我记下了，先按现在的方案继续。"
        for i in range(0, len(reply), 6):
            yield f"event: token\ndata: {json.dumps({'t': reply[i:i+6]}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.02)
        yield f"event: intent\ndata: {json.dumps(intent.to_dict(), ensure_ascii=False)}\n\n"
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
async def export_project(pid: str, req: ExportReq):
    p = DB.get("projects", pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    # 真实素材优先：取该项目已生成完成的 video 素材拼合成片。
    # 无真实素材 → 明确拒绝（409），不再生成任何演示片。
    src = req.source_path
    if not src:
        rows = DB.list(
            "SELECT local_path FROM assets WHERE project_id=? AND kind='video' ORDER BY created_at",
            (pid,),
        )
        real = [r["local_path"] for r in rows if Path(r["local_path"]).exists()]
        src = real[0] if real else None
    if not src or not Path(src).exists():
        raise HTTPException(409, {
            "code": "E4002", "message": "还没有真实画面可以导出",
            "hint": "请先完成第 6 步生成真实画面。没有素材时不会生成演示片。",
        })
    result = await PUBLISH.compose(src, ai_badge=True)  # 强制 true，忽略 req.ai_badge
    DB.insert("assets", {
        "id": result["work_id"], "project_id": pid, "kind": "work",
        "local_path": result["local_path"], "sha256": "pending",
        "size_bytes": result["size_bytes"],
    })
    DB.execute("UPDATE projects SET status='DELIVER' WHERE id=?", (pid,))
    return result
@app.get("/api/works", dependencies=[Depends(auth)])
def list_works():
    return {"items": DB.list("SELECT * FROM assets WHERE kind='work' ORDER BY created_at DESC")}
@app.get("/api/works/{work_id}/caption", dependencies=[Depends(auth)])
def work_caption(work_id: str, body: str = ""):
    work = DB.get("assets", work_id)
    if not work or work["kind"] != "work":
        raise HTTPException(404, "作品不存在")
    p = DB.get("projects", work["project_id"])
    name = p["name"] if p else "未命名项目"
    return {"caption": PUBLISH.caption(name, 1, body), "cached": False}
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
            c.execute("UPDATE model_configs SET is_active=0 WHERE slot=?", (slot,))
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
            "error": error, "mock": False}
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
@app.post("/api/projects/{pid}/generation/start", dependencies=[Depends(auth)])
async def generation_start(pid: str, req: GenStartReq = GenStartReq()):
    """设计 §6.4：开始生成批次。冻结在提交前，额度不足时 E2001。"""
    p = DB.get("projects", pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    # 前置校验：视频能力必须已配置并通过真实连接测试，否则拒绝生成（无 Mock 兜底）
    ensure_providers("video")
    if not REGISTRY.has_ability("video"):
        raise HTTPException(400, {
            "code": "E4001", "message": "还没有配置可用的视频模型",
            "hint": "请先到「设置 → 生成视频」填写服务地址和模型，并点「测试连接」通过后再开始",
        })
    wallet = LEDGER.wallet()
    if wallet["balance"] < PRICE_PER_SHOT_ESTIMATE * req.shot_count:
        raise HTTPException(400, {
            "code": "E2001", "message": "额度不够跑完这批",
            "need": PRICE_PER_SHOT_ESTIMATE * req.shot_count,
            "balance": wallet["balance"],
        })
    batch = await GENERATIONS.start(pid, req.shot_count)
    return {"batch_id": batch.id, "queued": req.shot_count,
            "route_reason": "按镜头重要性自动分配：重要镜头优先自带模型，过渡镜头走平台额度"}
PRICE_PER_SHOT_ESTIMATE = 9.0
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
    freeze_id = LEDGER.freeze(req.duration_s * 0.9, "smoke", route.provider_id, "video")
    try:
        tid = await provider.submit(VideoGenRequest(prompt=req.prompt, duration_s=req.duration_s, ratio=req.ratio))
        result = await provider.poll(tid)
    except Exception as exc:  # noqa: BLE001 - 边界：任何 Provider 异常都要退回冻结
        LEDGER.settle(freeze_id, 0, False, "provider_error")
        raise HTTPException(502, f"生成失败：{exc}")
    LEDGER.settle(freeze_id, result.raw_cost_estimate, result.ok, result.fail_reason)
    return {
        "task_id": tid, "ok": result.ok, "asset_ref": result.asset_ref,
        "route_reason": route.reason, "wallet": LEDGER.wallet(),
    }
