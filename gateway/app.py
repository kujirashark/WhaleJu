"""云网关骨架：鉴权/积分/转发（设计 v3.1 §6.6）。
硬约束：无存储、无素材留存；日志只记提示词哈希。
Redis 键与 Lua 原子扣减见设计文档；本骨架用内存模拟以便本地联调。
"""
from __future__ import annotations
import hashlib
import os
import time
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
app = FastAPI(title="鲸鲨漫剧网关", version="v1-w4")
# 内存态演示（生产替换为 Redis）；按 uid 隔离
_WALLETS: dict[str, float] = {}
_TASKS: dict[str, dict] = {}
_API_TOKEN = os.getenv("MANGJU_GATEWAY_TOKEN", "dev-gateway-token")
class GenReq(BaseModel):
    request_id: str = Field(min_length=6)   # 幂等键
    prompt: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)
def auth(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "缺少 Token")
    token = authorization[7:]
    if token != _API_TOKEN:
        raise HTTPException(401, "Token 无效")
    return "u_local"
def _prompt_hash(prompt: str) -> str:
    """日志脱敏：提示词只留哈希，不存全文。"""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
@app.get("/v1/wallet")
def wallet(uid: str = Depends(auth)):
    return {"balance": _WALLETS.get(uid, 100.0), "frozen": 0.0, "ledger_version": 0}
@app.post("/v1/generate/{ability}", status_code=202)
async def generate(ability: str, req: GenReq, uid: str = Depends(auth)):
    if ability not in ("text", "image", "video", "speech"):
        raise HTTPException(400, "未知能力")
    balance = _WALLETS.get(uid, 100.0)
    cost = 0.9 * req.params.get("duration_s", 5)
    if balance < cost:
        raise HTTPException(402, {"code": "G4001", "message": "额度不足"})
    # 幂等：同一 request_id 直接返回原任务，不二次扣费
    if req.request_id in _TASKS:
        return _TASKS[req.request_id]
    task_id = "gt_" + hashlib.sha256(req.request_id.encode()).hexdigest()[:16]
    _WALLETS[uid] = balance - cost
    task = {
        "task_id": task_id, "state": "done", "units_used": cost,
        "credits_charged": cost, "prompt_hash": _prompt_hash(req.prompt),
        "created_at": time.time(),
    }
    _TASKS[req.request_id] = task
    return {"task_id": task_id}
@app.get("/v1/tasks/{task_id}")
def task_status(task_id: str, uid: str = Depends(auth)):
    for t in _TASKS.values():
        if t["task_id"] == task_id:
            return {k: t[k] for k in ("state", "units_used", "credits_charged")}
    raise HTTPException(404, "任务不存在")
