"""对话驱动的流程：界面撤掉流程按钮后，agent 必须能自己推进。
背景：用户要求"各个界面的按钮都不出现，统一在下面聊天框里跟 agent 沟通"。
这意味着 agent 不能只会聊天，还得能：
- 识别"确认/好了/下一步"这类推进语（confirm_step）
- 识别"写第 2 集"这类续写语（write_next_episode）
- 说出具体是确认哪一步（回复文案按项目状态定制）
"""
from __future__ import annotations
import json
import os
import tempfile
os.environ.setdefault("MANGJU_DATA_DIR", tempfile.mkdtemp(prefix="mangju-test-w9-"))
from fastapi.testclient import TestClient
import pytest
from engine.app.main import app, DB, LOCAL_TOKEN
from engine.app.agent.agent import ConversationAgent, ALLOWED_TOOLS
HEADERS = {"X-Local-Token": LOCAL_TOKEN}
@pytest.fixture(autouse=True)
def clean_db():
    DB.init_schema()
    with DB.tx() as c:
        for t in ("generation_tasks", "shots", "episodes", "checkpoints", "assets",
                  "usage_events", "characters", "projects", "model_configs"):
            c.execute(f"DELETE FROM {t}")
def _events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.split("\n\n"):
        ev = dt = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                dt = line[5:].strip()
        if ev and dt:
            try:
                out.append((ev, json.loads(dt)))
            except json.JSONDecodeError:
                out.append((ev, dt))
    return out
# ── 意图识别 ──────────────────────────────────────────────────────
@pytest.mark.parametrize("text,op", [
    # 推进类
    ("确认", "confirm_step"),
    ("好了", "confirm_step"),
    ("可以了", "confirm_step"),
    ("下一步", "confirm_step"),
    ("行", "confirm_step"),
    ("确认剧本", "confirm_step"),
    ("确认形象", "confirm_step"),
    ("确认这一版", "confirm_step"),
    # 流程类
    ("写剧本", "gen_script"),
    ("拆镜头", "gen_shots"),
    ("生成画面", "gen_video"),
    ("导出成片", "export_video"),
    ("生成定妆图", "gen_characters"),
    # 修改类
    ("重新生成这一稿", "regen_script"),
    ("重写剧本", "regen_script"),
    ("重新生成定妆图", "gen_characters"),
    ("第二集节奏太快了", "adjust_pacing"),
    # 续写
    ("写第 2 集", "write_next_episode"),
    ("下一集", "write_next_episode"),
    ("接着写", "write_next_episode"),
    # 问答
    ("你好", "answer_question"),
    ("这剧讲啥", "answer_question"),
    ("确认一下这剧讲啥", "answer_question"),
])
def test_agent_classify(text, op):
    assert ConversationAgent().classify(text) == op, text
def test_new_ops_are_allowed():
    """新意图必须在白名单里，否则前端点了也执行不了。"""
    assert "confirm_step" in ALLOWED_TOOLS
    assert "write_next_episode" in ALLOWED_TOOLS
# ── 回复文案：要说清是哪一步 ──────────────────────────────────────
def test_confirm_reply_names_the_step():
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "只做一集"}, headers=HEADERS).json()["id"]
    # 剧本生成后状态机应停在 CP1_PENDING（等你确认剧本）
    DB.execute("UPDATE projects SET script_json=?, status='CP1_PENDING' WHERE id=?",
               (json.dumps({"title": "剧", "episodes": [{"idx": 1, "title": "一", "script": "正文"}]},
                           ensure_ascii=False), pid))
    with client.stream("POST", "/api/chat/stream", headers=HEADERS,
                       json={"message": "确认", "project_id": pid}) as r:
        events = _events("".join(r.iter_text()))
    reply = "".join(d.get("t", "") for e, d in events if e == "token")
    assert "剧本" in reply, reply
    intent = next(d for e, d in events if e == "intent")
    assert intent["op"] == "confirm_step"
    assert intent["needs_confirm"] is True
def test_write_next_episode_reply_says_which_episode():
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "共三集短剧"}, headers=HEADERS).json()["id"]
    DB.execute("UPDATE projects SET script_json=? WHERE id=?",
               (json.dumps({"title": "剧", "episodes": [{"idx": 1, "title": "一", "script": "正文"}]},
                           ensure_ascii=False), pid))
    with client.stream("POST", "/api/chat/stream", headers=HEADERS,
                       json={"message": "写第 2 集", "project_id": pid}) as r:
        events = _events("".join(r.iter_text()))
    reply = "".join(d.get("t", "") for e, d in events if e == "token")
    assert "第 2 集" in reply, reply
    assert "共 3 集" in reply, reply
def test_confirm_without_project_says_so():
    client = TestClient(app)
    with client.stream("POST", "/api/chat/stream", headers=HEADERS,
                       json={"message": "确认", "project_id": None}) as r:
        events = _events("".join(r.iter_text()))
    reply = "".join(d.get("t", "") for e, d in events if e == "token")
    assert "项目" in reply, reply
def test_answer_question_has_no_confirm_bar():
    """问答类不该弹确认条（needs_confirm=false），否则用户被无意义的确认打断。"""
    client = TestClient(app)
    with client.stream("POST", "/api/chat/stream", headers=HEADERS,
                       json={"message": "你好", "project_id": None}) as r:
        events = _events("".join(r.iter_text()))
    intent = next(d for e, d in events if e == "intent")
    assert intent["needs_confirm"] is False
    assert intent["op"] == "answer_question"
