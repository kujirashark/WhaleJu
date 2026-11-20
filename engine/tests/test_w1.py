"""W1 测试：状态机、存储、计费、API 冒烟。"""
from __future__ import annotations
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from engine.app.main import app, DB, LOCAL_TOKEN
from engine.app.storage.db import Database
from engine.app.storage.util import ulid
from engine.app.workflow.state_machine import TRANSITIONS, GuardError, WorkflowEngine
HEADERS = {"X-Local-Token": LOCAL_TOKEN}
@pytest.fixture(autouse=True)
def clean_db():
    DB.init_schema()
    with DB.tx() as c:
        for t in ("generation_tasks", "shots", "episodes", "checkpoints", "assets", "usage_events", "characters", "projects"):
            c.execute(f"DELETE FROM {t}")
        c.execute("UPDATE credit_wallet SET balance=86.4, frozen=0 WHERE id=1")
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
def test_generation_mock_roundtrip():
    """W1 一票否决验收：submit→poll→冻结→结算，全链路零外部 API。"""
    client = TestClient(app)
    r = client.post("/api/generation/submit", json={
        "prompt": "黄昏院子里的孩子奔跑", "duration_s": 5, "ratio": "9:16", "importance": "transition",
    }, headers=HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["task_id"].startswith("mt_")
    assert "route_reason" in body and body["route_reason"]
    assert body["wallet"]["frozen"] == 0  # 结算后冻结已归零
    assert body["wallet"]["balance"] < 86.4  # 实扣已发生
    with DB.read() as c:
        used = c.execute("SELECT COUNT(*) FROM usage_events WHERE ok=1 AND source='proxy'").fetchone()[0]
    assert used >= 1
def test_model_config_hides_credential():
    """凭证只入库密文；任何接口不回显明文（Never 层安全规则）。"""
    client = TestClient(app)
    secret = "sk-test-abcdefghijklmnop"
    r = client.put("/api/model-configs/text", json={
        "source": "owned", "provider_kind": "openai_compat", "name": "我的 DeepSeek",
        "endpoint": "https://api.deepseek.com/v1", "credential": secret,
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
def test_model_config_rejects_local_without_endpoint():
    client = TestClient(app)
    r = client.put("/api/model-configs/video", json={
        "source": "local", "provider_kind": "ollama", "name": "本地 Ollama", "credential": None,
    }, headers=HEADERS)
    assert r.status_code == 400
def test_route_reason_present():
    from engine.app.main import REGISTRY
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
