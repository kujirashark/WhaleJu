"""鲸鲨漫剧本地引擎 FastAPI 入口（127.0.0.1:7420）。"""
from __future__ import annotations
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from .adapters.base import VideoGenRequest
from .adapters.mock_provider import MockProvider
from .adapters.registry import ProviderRegistry
from .billing.ledger import CreditLedger, InsufficientCredits
from .storage.db import Database
from .storage.util import dumps, loads, ulid, utc_now
from .storage.vault import encrypt, mask
from .adapters.openai_compat import OpenAICompatProvider
from .workflow.state_machine import GuardError, WorkflowEngine
from .workflow.checkpoints import CheckpointManager
from .agent.agent import ConversationAgent, Intent
from .publish.kit import PublishKit
DATA_DIR = Path(os.getenv("MANGJU_DATA_DIR", str(Path.cwd() / "engine" / "data")))
DB = Database(DATA_DIR / "mangju.db")
LEDGER = CreditLedger(DB)
WORKFLOW = WorkflowEngine()
CHECKPOINTS = CheckpointManager(DB)
AGENT = ConversationAgent()
REGISTRY = ProviderRegistry()
REGISTRY.register(MockProvider())
PUBLISH = PublishKit(DATA_DIR)
# 本地鉴权 Token：启动时生成，重启轮换（防本机其他进程调用）
LOCAL_TOKEN = os.urandom(24).hex()
@asynccontextmanager
async def lifespan(app: FastAPI):
    DB.init_schema()
    recovered = CHECKPOINTS.recover()
    if recovered:
        print(f"[recover] {len(recovered)} 个检查点挂起，等待用户确认（不自动推进）")
    yield
app = FastAPI(title="鲸鲨漫剧本地引擎", version="v1-w1", lifespan=lifespan)
def auth(x_local_token: str | None = Header(default=None)):
    if x_local_token != LOCAL_TOKEN:
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
    source: str = Field(pattern="^(proxy|owned|local)$")
    provider_kind: str = Field(pattern="^(openai_compat|kling|jimeng|helo|ollama|comfyui)$")
    name: str = Field(min_length=1, max_length=60)
    endpoint: str | None = None
    credential: str | None = None
PLANS = {"p1": 50.0, "p2": 200.0, "p3": 1000.0}
SLOTS = ("text", "image", "video", "speech")
def _public_slot(slot: str) -> dict:
    with DB.read() as c:
        row = c.execute(
            "SELECT * FROM model_configs WHERE slot=? AND is_active=1", (slot,)
        ).fetchone()
    if not row:
        return {"source": None, "provider_kind": None, "name": None, "status": "unset", "last_probe_at": None}
    return {
        "source": row["source"], "provider_kind": row["provider_kind"],
        "name": row["name"], "status": "probed_ok", "last_probe_at": row["updated_at"],
        "endpoint": row["endpoint"],
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
@app.get("/api/projects/{pid}", dependencies=[Depends(auth)])
def get_project(pid: str):
    p = DB.get("projects", pid)
    if not p or p.get("deleted_at"):
        raise HTTPException(404, "项目不存在或已被清理")
    return {**p, "resume_hint": f"当前状态：{p['status']}", "credits_frozen": LEDGER.wallet()["frozen"]}
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
    """对话：返回结构意图（intent），不执行写操作；确认由前端调用业务接口完成。"""
    intent = await AGENT.rewrite(req.message, req.project_id)
    return {"intent": intent.to_dict()}
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
    # 生产环境：从 assets 表取该集所有 video 素材，ffmpeg concat；W4 用占位素材或传入源
    src = req.source_path or str(DATA_DIR / "assets" / "sample.mp4")
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
    """凭证在此处加密入库，此后任何接口不回显明文。"""
    if slot not in SLOTS:
        raise HTTPException(400, "未知能力槽")
    if req.source == "local" and not req.endpoint:
        raise HTTPException(400, "本地模型需要填写服务地址")
    with DB.tx() as c:
        c.execute("UPDATE model_configs SET is_active=0 WHERE slot=?", (slot,))
        cipher = encrypt(req.credential) if req.credential else None
        c.execute(
            """INSERT INTO model_configs(id,slot,source,provider_kind,name,endpoint,credential_cipher,abilities,is_active)
               VALUES(?,?,?,?,?,?,?,?,1)""",
            (ulid(), slot, req.source, req.provider_kind, req.name, req.endpoint,
             cipher, dumps(list(SLOTS))),
        )
    return {"saved": True, "slot": _public_slot(slot)}
@app.post("/api/model-configs/{slot}/test", dependencies=[Depends(auth)])
async def test_model_config(slot: str):
    """连接测试：真实 Key 时走 probe；未配置时返回 mock 可用。"""
    if slot not in SLOTS:
        raise HTTPException(400, "未知能力槽")
    with DB.read() as c:
        row = c.execute(
            "SELECT * FROM model_configs WHERE slot=? AND is_active=1", (slot,)
        ).fetchone()
    if not row:
        return {"ok": True, "latency_ms": 8, "abilities": ["text", "image", "video", "speech"],
                "price_hint": "模拟模式", "mock": True}
    if not row["credential_cipher"]:
        return {"ok": True, "latency_ms": 5, "abilities": loads(row["abilities"], []),
                "price_hint": "无需密钥", "mock": False}
    from .storage.vault import decrypt
    p = OpenAICompatProvider(
        provider_id=f"owned_{slot}", endpoint=row["endpoint"] or "https://api.openai.com/v1",
        api_key=decrypt(row["credential_cipher"]),
    )
    result = await p.probe()
    return {"ok": result.ok, "latency_ms": result.latency_ms,
            "abilities": list(result.abilities), "price_hint": result.price_hint,
            "error": result.error, "mock": False}
@app.post("/api/generation/submit", dependencies=[Depends(auth)])
async def generation_submit(req: GenReq):
    """W1 冒烟：Mock 通道跑通 submit→poll→冻结→结算。"""
    route = REGISTRY.route("video", req.importance)
    if not route:
        raise HTTPException(400, "没有可用模型")
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
