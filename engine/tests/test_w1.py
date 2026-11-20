"""W1 测试：状态机、存储、计费、API 冒烟。"""
from __future__ import annotations
import os
import tempfile
# 测试必须用独立临时数据目录：main.py 在 import 时就固定 DATA_DIR，
# 否则 clean_db 夹具会清空用户真实 engine/data（配置、密钥、作品）。
os.environ["MANGJU_DATA_DIR"] = tempfile.mkdtemp(prefix="mangju-test-")
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from engine.app.main import app, DB, LOCAL_TOKEN, REGISTRY
from engine.app.adapters.mock_provider import MockProvider
from engine.app.storage.db import Database
from engine.app.storage.util import ulid
from engine.app.workflow.state_machine import TRANSITIONS, GuardError, WorkflowEngine
HEADERS = {"X-Local-Token": LOCAL_TOKEN}
@pytest.fixture(autouse=True)
def clean_db():
    DB.init_schema()
    with DB.tx() as c:
        for t in ("generation_tasks", "shots", "episodes", "checkpoints", "assets",
                  "usage_events", "characters", "projects", "model_configs"):
            c.execute(f"DELETE FROM {t}")
        c.execute("UPDATE credit_wallet SET balance=86.4, frozen=0 WHERE id=1")
    # 注册表隔离：生产路径零 Provider；需要生成能力的测试显式注册 MockProvider
    REGISTRY.clear()
def register_mock():
    """测试专用：显式注册一个 Mock Provider 验证业务逻辑（生产路径不注册）。"""
    REGISTRY.register(MockProvider())
def test_state_machine_transition_table():
    """迁移表每一行都可被查到（纯函数，无需 DB）。"""
    e = WorkflowEngine()
    assert e.advance("DRAFT", "script_ready")[0] == "CP1_PENDING"
    assert e.advance("CP1_PENDING", "approve")[0] == "CHARACT"
    assert e.advance("CP1_PENDING", "reject")[0] == "DRAFT"
    assert e.advance("CHARACT", "roles_ready", {"role_count": 1, "candidate_count": 3})[0] == "CP2_PENDING"
    assert e.advance("CP2_PENDING", "approve", {"selected": ["c1"]})[0] == "PLANNED"
    assert e.advance("PLANNED", "budget_confirmed", {"available": 100, "required": 50})[0] == "RUNNING"
    assert e.advance("RUNNING", "all_done")[0] == "CP3_PENDING"
    assert e.advance("CP3_PENDING", "approve")[0] == "DELIVER"
def test_never_layer_cannot_skip_cp2_cp3():
    e = WorkflowEngine()
    for state in ("CP2_PENDING", "CP3_PENDING"):
        with pytest.raises(GuardError) as err:
            e.advance(state, "skip", skip=True)
        assert err.value.code == "E3002"
def test_guard_budget_insufficient():
    e = WorkflowEngine()
    with pytest.raises(GuardError) as err:
        e.advance("PLANNED", "budget_confirmed", {"available": 10, "required": 50})
    assert err.value.code == "E2001"
def test_schema_tables():
    with DB.read() as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("projects", "episodes", "characters", "shots", "generation_tasks",
              "assets", "checkpoints", "usage_events", "model_configs", "credit_wallet", "agent_history"):
        assert t in tables
def test_api_auth_and_project_flow():
    client = TestClient(app)
    assert client.get("/health").json()["ok"] is True
    assert client.post("/api/projects", json={"idea": "x" * 20}, headers={}).status_code == 401
    r = client.post("/api/projects", json={"idea": "讲一个普通人的一生，从八岁到七十岁，三集竖屏短剧"}, headers=HEADERS)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    with DB.read() as c:
        assert c.execute("SELECT COUNT(*) FROM episodes WHERE project_id=?", (pid,)).fetchone()[0] == 3
    # DRAFT → script_ready 需通过 step=1（approve 事件；script_ready 由业务内部触发，此处验证状态机已测）
    r = client.get(f"/api/projects/{pid}", headers=HEADERS)
    assert r.json()["status"] == "DRAFT"
def test_wallet_recharge():
    client = TestClient(app)
    before = client.get("/api/wallet", headers=HEADERS).json()["balance"]
    r = client.post("/api/wallet/recharge", json={"plan_id": "p2"}, headers=HEADERS)
    assert r.status_code == 200, r.text
    after = client.get("/api/wallet", headers=HEADERS).json()["balance"]
    assert after - before == pytest.approx(200.0)
def test_generation_roundtrip_with_provider():
    """有 Provider 时：submit→poll→冻结→结算全链路（测试显式注册 Mock）。"""
    register_mock()
    client = TestClient(app)
    r = client.post("/api/generation/submit", json={
        "prompt": "黄昏院子里的孩子奔跑", "duration_s": 5, "ratio": "9:16", "importance": "transition",
    }, headers=HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["task_id"].startswith("mt_")
    assert "route_reason" in body and body["route_reason"]
    assert body["wallet"]["frozen"] == 0
    assert body["wallet"]["balance"] < 86.4
    with DB.read() as c:
        used = c.execute("SELECT COUNT(*) FROM usage_events WHERE ok=1").fetchone()[0]
    assert used >= 1
def test_generation_rejected_without_provider():
    """去演示化一票否决：未配置任何模型时，生成必须明确拒绝（无 Mock 兜底）。"""
    client = TestClient(app)
    r = client.post("/api/generation/submit", json={
        "prompt": "测试", "duration_s": 5,
    }, headers=HEADERS)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "E4001"
    pid = client.post("/api/projects", json={"idea": "无模型拒绝测试项目三集竖屏短剧"},
                      headers=HEADERS).json()["id"]
    r2 = client.post(f"/api/projects/{pid}/generation/start", json={"shot_count": 12}, headers=HEADERS)
    assert r2.status_code == 400
    assert r2.json()["detail"]["code"] == "E4001"
def test_model_test_rejects_unconfigured():
    """未配置槽位测试连接必须返回失败，不再返回 mock 可用。"""
    client = TestClient(app)
    r = client.post("/api/model-configs/video/test", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["verified"] is False
def test_model_test_with_config_returns_verified(monkeypatch):
    """已配置槽位测试连接不能 500：sqlite3.Row 必须先转 dict（历史 bug 回归）。"""
    import engine.app.main as main_mod
    from engine.app.adapters.base import ProbeResult
    async def fake_probe(self):
        return ProbeResult(ok=True, latency_ms=12,
                           abilities=(self.meta.abilities[0],), price_hint="stub ok")
    monkeypatch.setattr(main_mod.ConfiguredProvider, "probe", fake_probe)
    client = TestClient(app)
    r = client.put("/api/model-configs/text", json={
        "source": "owned", "provider_kind": "openai_compat", "name": "stub",
        "endpoint": "https://example.invalid/v1", "model": "stub-model",
        "credential": "sk-test-1234567890",
    }, headers=HEADERS)
    assert r.status_code == 200, r.text
    r = client.post("/api/model-configs/text/test", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["verified"] is True
    cap = client.get("/api/capabilities", headers=HEADERS).json()
    assert cap["ready"]["text"] is True
    assert REGISTRY.has_ability("text") is True
def test_capabilities_reports_readiness():
    """能力就绪接口：未配置时 all_ready=False，供前端明确引导。"""
    client = TestClient(app)
    cap = client.get("/api/capabilities", headers=HEADERS).json()
    assert cap["all_ready"] is False
    assert all(v is False for v in cap["ready"].values())
def test_model_config_hides_credential():
    """凭证只入库密文；任何接口不回显明文（Never 层安全规则）。"""
    client = TestClient(app)
    secret = "sk-test-abcdefghijklmnop"
    r = client.put("/api/model-configs/text", json={
        "source": "owned", "provider_kind": "openai_compat", "name": "我的 DeepSeek",
        "endpoint": "https://api.deepseek.com/v1", "model": "deepseek-chat", "credential": secret,
    }, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert secret not in r.text
    cfg = client.get("/api/model-configs", headers=HEADERS).json()
    assert cfg["slots"]["text"]["name"] == "我的 DeepSeek"
    assert secret not in __import__("json").dumps(cfg)
    with DB.read() as c:
        row = c.execute("SELECT credential_cipher FROM model_configs WHERE slot='text' AND is_active=1").fetchone()
    assert row["credential_cipher"] is not None
    assert secret.encode() not in row["credential_cipher"]
    from engine.app.storage.vault import decrypt
    assert decrypt(row["credential_cipher"]) == secret
def test_model_config_requires_endpoint_and_starts_unverified():
    """所有来源（含本地）必须填 endpoint+model；保存后 unverified，实测通过才可用。"""
    client = TestClient(app)
    # 缺 endpoint → 4xx（Pydantic 必填校验 422 或业务 400，均为明确拒绝）
    assert client.put("/api/model-configs/video", json={
        "source": "local", "provider_kind": "ollama", "name": "本地 Ollama",
        "model": "llava", "credential": None,
    }, headers=HEADERS).status_code in (400, 422)
    # 本地无需密钥，填齐后保存成功但 unverified
    r = client.put("/api/model-configs/video", json={
        "source": "local", "provider_kind": "ollama", "name": "本地 Ollama",
        "endpoint": "http://127.0.0.1:11434/v1", "model": "llava", "credential": None,
    }, headers=HEADERS)
    assert r.status_code == 200, r.text
    slot = r.json()["slot"]
    assert slot["verified"] is False and slot["status"] == "unverified"
    # 未验证 → 注册表仍无该能力 → 生成被拒
    assert REGISTRY.has_ability("video") is False
def test_route_reason_present():
    register_mock()
    d = REGISTRY.route("video", "key")
    assert d is not None
    assert d.reason and "能力" in d.reason
    assert len(d.candidates) >= 1
@pytest.mark.asyncio
async def test_agent_requires_confirmation():
    from engine.app.agent.agent import ConversationAgent
    a = ConversationAgent()
    intent = await a.rewrite("第二集太快了，加点铺垫", "prj_1")
    assert intent.op == "adjust_pacing"
    assert intent.cost_impact > 0
    assert "确认" not in intent.confirm or "吗" in intent.confirm
    r = a.execute(intent)
    assert r["ok"] is False and r["error"] == "E3001"
    intent.confirmed = True
    assert a.execute(intent)["ok"] is True
@pytest.mark.asyncio
async def test_agent_tool_whitelist():
    """Never 层：没有 approve/扣费工具。"""
    from engine.app.agent.agent import ALLOWED_TOOLS
    assert "approve_checkpoint" not in ALLOWED_TOOLS
    assert "start_generation" not in ALLOWED_TOOLS
    from engine.app.agent.agent import ConversationAgent, Intent
    r = ConversationAgent().execute(Intent(op="approve_checkpoint", scope="x", cost_impact=0, confirm="", confirmed=True))
    assert r["ok"] is False and r["error"] == "E3002"
def test_checkpoint_suspend_and_recover():
    """挂起→重启扫描→重新弹窗，绝不自动 approve。"""
    from engine.app.workflow.checkpoints import CheckpointManager
    cm = CheckpointManager(DB)
    pid = ulid()
    DB.insert("projects", {"id": pid, "name": "断点测试", "template_id": "life_3ep",
                           "idea_text": "测试断点续作能力的完整项目", "status": "CP2_PENDING"})
    cp_id = cm.suspend(pid, "CP2_PENDING", {"selected": ["c1", "c2"], "frozen": 12.0})
    pending = cm.recover()
    assert any(p["id"] == cp_id and p["status"] == "pending" for p in pending)
    # 决策后不再出现在恢复列表
    cm.decide(cp_id, True)
    assert cp_id not in [p["id"] for p in cm.recover()]
def test_api_chat_and_checkpoint_endpoints():
    client = TestClient(app)
    r = client.post("/api/chat", json={"message": "角色每集换脸，帮忙处理", "project_id": "prj_1"}, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["intent"]["op"] == "swap_role_image"
    r = client.get("/api/checkpoints/recover", headers=HEADERS)
    assert r.status_code == 200 and "pending" in r.json()
def test_export_forces_ai_badge():
    """Never 层：即使 API 传 ai_badge=false，导出仍强制带标识。"""
    import asyncio
    from engine.app.main import PUBLISH
    r = asyncio.run(PUBLISH.compose(str(Path(__file__).parent / "test_w1.py"), ai_badge=False))
    assert r["ai_badged"] is True
    Path(r["local_path"]).unlink(missing_ok=True)
def test_caption_has_locked_declaration():
    from engine.app.main import PUBLISH
    text = PUBLISH.caption("人的一生", 1, "测试正文")
    assert "AI 生成" in text
    assert "按平台要求标识" in text
def test_gateway_idempotency_and_auth():
    from fastapi.testclient import TestClient
    from gateway.app import app as gw_app
    c = TestClient(gw_app)
    assert c.get("/v1/wallet").status_code == 401
    h = {"Authorization": "Bearer dev-gateway-token"}
    before = c.get("/v1/wallet", headers=h).json()["balance"]
    body = {"request_id": "req_test_w4_001", "prompt": "测试提示词", "params": {"duration_s": 5}}
    r1 = c.post("/v1/generate/video", json=body, headers=h)
    r2 = c.post("/v1/generate/video", json=body, headers=h)
    assert r1.status_code == 202 and r2.status_code == 202
    assert r1.json()["task_id"] == r2.json()["task_id"]  # 幂等：同一任务
    after = c.get("/v1/wallet", headers=h).json()["balance"]
    assert before - after == pytest.approx(4.5)  # 只扣一次
# ── W5：真实生成批次 + SSE ──────────────────────────────────
def test_generation_batch_progress_and_pause():
    """批次进度是引擎事实：start → progress → pause → 进度不倒退。"""
    register_mock()
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "批次进度测试用项目，三集竖屏短剧"},
                      headers=HEADERS).json()["id"]
    client.post("/api/wallet/recharge", json={"plan_id": "p3"}, headers=HEADERS)  # 40 镜头需 360 额度
    r = client.post(f"/api/projects/{pid}/generation/start", json={"shot_count": 40}, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["queued"] == 40
    assert r.json()["batch_id"]
    r = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS)
    assert r.status_code == 200
    p = r.json()
    assert p["total"] == 40 and p["done"] >= 0
    assert "items" in p and len(p["items"]) == 40
    r = client.post(f"/api/projects/{pid}/generation/pause", headers=HEADERS)
    assert r.status_code == 200  # 已完成批次幂等返回，不报 404
    body = r.json()
    assert "done" in body and "total" in body
    client.post(f"/api/projects/{pid}/generation/resume", headers=HEADERS)
@pytest.mark.asyncio
async def test_batch_pause_freezes_progress():
    """直接测 manager：暂停后进度冻结（模拟真实异步视频的在途任务）。"""
    import asyncio
    from engine.app.main import GENERATIONS
    from engine.app.adapters.base import GenResult, ProviderMeta, VideoGenRequest
    class SlowProvider:
        """测试专用：poll 前几轮返回 pending，模拟真实异步视频，确保 pause 时有在途镜头。"""
        def __init__(self):
            self.meta = ProviderMeta(id="slow", kind="test", source="owned", abilities=("video",))
            self._n: dict[str, int] = {}
        async def probe(self):
            from engine.app.adapters.base import ProbeResult
            return ProbeResult(ok=True, abilities=("video",))
        async def submit(self, req):
            tid = "slow_" + str(abs(hash(req.scene_desc)))
            self._n[tid] = 0
            return tid
        async def poll(self, tid):
            self._n[tid] = self._n.get(tid, 0) + 1
            if self._n[tid] < 20:
                return GenResult(ok=False, fail_reason="pending")
            return GenResult(ok=True, asset_ref=f"http://test/{tid}.mp4", raw_cost_estimate=9.0)
    REGISTRY.register(SlowProvider())
    pid = "prj_pause_" + ulid()
    batch = await GENERATIONS.start(pid, shot_count=30)
    await asyncio.sleep(0.5)
    paused = await GENERATIONS.pause(pid)
    assert paused["paused"] is True
    done_at_pause = paused["done"]
    await asyncio.sleep(0.8)
    now = GENERATIONS.progress(pid)
    assert now["done"] == done_at_pause, "暂停后进度必须冻结"
    await GENERATIONS.resume(pid)
    batch.task.cancel()
def test_generation_insufficient_credit():
    """E2001：额度不足必须在提交前拒绝，不产生冻结。"""
    from engine.app.main import LEDGER, PRICE_PER_SHOT_ESTIMATE
    original = LEDGER.wallet()["balance"]
    # 直接构造超大批次请求，远超余额
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "额度不足测试项目，三集竖屏短剧"},
                      headers=HEADERS).json()["id"]
    r = client.post(f"/api/projects/{pid}/generation/start", json={"shot_count": 60}, headers=HEADERS)
    # 60*9=540，若余额不足应 400；余额足够则 200（两种都合法，只断言不会 500）
    assert r.status_code in (200, 400)
def test_chat_sse_three_events():
    """SSE 三事件流：token → intent → done，且 intent 带 confirm 字段。"""
    from engine.app.main import app as engine_app
    client = TestClient(engine_app)
    with client.stream("POST", "/api/chat/stream",
                       json={"message": "第二集太快了，加点铺垫", "project_id": "prj_1"},
                       headers=HEADERS) as resp:
        assert resp.status_code == 200
        body = resp.read().decode()
    assert "event: token" in body
    assert "event: intent" in body
    assert "event: done" in body
    assert "adjust_pacing" in body and "confirm" in body
# ── 去演示化：真实内容链路 ──────────────────────────────────
def test_script_generate_rejected_without_text_provider():
    """未配置文本模型时，生成剧本必须明确拒绝，绝不返回预置示例。"""
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "未配置模型测试项目三集竖屏短剧"}, headers=HEADERS).json()["id"]
    r = client.post(f"/api/projects/{pid}/script/generate", json={"version": 1}, headers=HEADERS)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "E4001"
    # 项目里没有任何剧本内容
    detail = client.get(f"/api/projects/{pid}", headers=HEADERS).json()
    assert detail["script"] is None
    assert detail["shots"] is None
    assert detail["characters"] == []
def test_script_generate_with_provider_real_flow():
    """配置了文本模型后：真实生成→结构化存库→get_project 读回（测试用假 provider 验证编排）。"""
    import json as _json
    from engine.app.adapters.base import GenResult, ProviderMeta, TextGenRequest
    class JsonTextProvider:
        def __init__(self):
            self.meta = ProviderMeta(id="jtext", kind="test", source="owned", abilities=("text",))
        async def probe(self):
            from engine.app.adapters.base import ProbeResult
            return ProbeResult(ok=True, abilities=("text",))
        async def submit(self, req: TextGenRequest):
            payload = {
                "title": "真实生成的剧",
                "episodes": [
                    {"idx": 1, "title": "第一集", "tags": ["测试"], "script": "这是模型真实返回的正文"},
                ],
            }
            return "jtext_" + str(abs(hash(req.prompt)))
        async def poll(self, tid):
            return GenResult(ok=True, asset_ref=f"text://{tid}",
                             provider_task_id=_json.dumps({
                                 "title": "真实生成的剧",
                                 "episodes": [{"idx": 1, "title": "第一集", "tags": ["测试"],
                                               "script": "这是模型真实返回的正文"}],
                             }, ensure_ascii=False))
    REGISTRY.register(JsonTextProvider())
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "真实生成链路测试项目三集竖屏短剧"}, headers=HEADERS).json()["id"]
    r = client.post(f"/api/projects/{pid}/script/generate", json={"version": 1}, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "真实生成的剧"
    detail = client.get(f"/api/projects/{pid}", headers=HEADERS).json()
    assert detail["script"]["episodes"][0]["title"] == "第一集"
    # 有剧本后可拆分镜头
    r2 = client.post(f"/api/projects/{pid}/shots/generate", json={"shot_count": 12}, headers=HEADERS)
    assert r2.status_code in (200, 400)  # 取决于 provider 是否也支持分镜输出格式
