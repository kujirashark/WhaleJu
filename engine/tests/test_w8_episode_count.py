"""集数解析与逐集写作的回归测试。
背景：剧本集数曾经写死 3 集 —— 用户在首页说"只做一集"，引擎照样生成 3 集，
白烧 token 还会被限流截断。现在集数一律从用户想法里解析，没说就 1 集。
"""
from __future__ import annotations
import json
import os
import tempfile
os.environ["MANGJU_DATA_DIR"] = tempfile.mkdtemp(prefix="mangju-test-")
from fastapi.testclient import TestClient
import pytest
from engine.app.main import app, DB, LOCAL_TOKEN, REGISTRY
from engine.app.adapters.base import ProviderMeta
from engine.app.workflow.episode_spec import parse_episode_count
from engine.app.workflow.content import ContentGenerator
HEADERS = {"X-Local-Token": LOCAL_TOKEN}
@pytest.fixture(autouse=True)
def clean_db():
    DB.init_schema()
    with DB.tx() as c:
        for t in ("generation_tasks", "shots", "episodes", "checkpoints", "assets",
                  "usage_events", "characters", "projects", "model_configs"):
            c.execute(f"DELETE FROM {t}")
    REGISTRY.clear()
# ── 解析器 ────────────────────────────────────────────────────────
def test_parse_defaults_to_one_episode():
    """没说集数 = 1 集（不是 3 集）。"""
    assert parse_episode_count("小鲸流浪记") == (1, False)
    assert parse_episode_count("") == (1, False)
def test_parse_explicit_single_episode():
    for text in ("只做一集", "一集就好", "单集短剧", "先出一集看看"):
        count, explicit = parse_episode_count(text)
        assert count == 1, text
        assert explicit is True, text
def test_parse_multi_episode_numbers():
    cases = {
        "讲一个普通人的一生，从八岁到七十岁，三集竖屏短剧": 3,
        "做成 5 集": 5,
        "共10集": 10,
        "改成十二集": 12,
        "一部三集短剧": 3,
        "悬疑反转三集": 3,
        "二十集长剧": 20,
    }
    for text, want in cases.items():
        count, explicit = parse_episode_count(text)
        assert count == want, f"{text} -> {count}"
        assert explicit is True, text
def test_parse_ignores_non_episode_numbers():
    """年龄跨度、每集字数、"第 N 集"都不是集数。"""
    assert parse_episode_count("从1岁到100岁的一生") == (1, False)
    assert parse_episode_count("每集200字") == (1, False)
    assert parse_episode_count("第2集节奏太快了") == (1, False)
def test_parse_range_takes_lower_bound():
    assert parse_episode_count("2-3集")[0] == 2
    assert parse_episode_count("两三集")[0] == 2
def test_parse_caps_at_max():
    assert parse_episode_count("100集连续剧")[0] == 30
# ── 建项目：集数跟着想法走 ────────────────────────────────────────
def test_create_project_uses_parsed_episode_count():
    client = TestClient(app)
    # 没说集数 → 1 集
    r = client.post("/api/projects", json={"idea": "小鲸流浪记"}, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["episode_count"] == 1
    pid = r.json()["id"]
    with DB.read() as c:
        n = c.execute("SELECT COUNT(*) FROM episodes WHERE project_id=?", (pid,)).fetchone()[0]
    assert n == 1
    # 说了 3 集 → 3 集
    r = client.post("/api/projects", json={"idea": "悬疑反转三集短剧"}, headers=HEADERS)
    assert r.json()["episode_count"] == 3
    pid = r.json()["id"]
    with DB.read() as c:
        n = c.execute("SELECT COUNT(*) FROM episodes WHERE project_id=?", (pid,)).fetchone()[0]
    assert n == 3
def test_project_detail_exposes_target_count():
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "只做一集"}, headers=HEADERS).json()["id"]
    detail = client.get(f"/api/projects/{pid}", headers=HEADERS).json()
    assert detail["episode_count"] == 1
# ── 提示词：集数不写死 ────────────────────────────────────────────
def test_script_prompt_follows_target_count():
    gen = ContentGenerator.__new__(ContentGenerator)  # 只测纯函数
    system, prompt = ContentGenerator._script_prompt("一个故事", total=1)
    assert "写 1 集" in system
    assert "1 集竖屏短剧" in prompt
    system, prompt = ContentGenerator._script_prompt("一个故事", total=4)
    assert "写 4 集" in system
    assert "4 集竖屏短剧" in prompt
    # 逐集写作：只写这一集，并带上前情
    system, prompt = ContentGenerator._script_prompt(
        "一个故事", total=3, episode_index=2,
        prev=[{"idx": 1, "title": "开端", "script": "他离开了家。"}],
    )
    assert "第 2 集" in system
    assert "只写第 2 集" in system
    assert "第 1 集" in prompt and "他离开了家" in prompt
def test_script_budget_scales_with_episodes():
    gen = ContentGenerator.__new__(ContentGenerator)
    assert ContentGenerator._script_budget(1) < ContentGenerator._script_budget(3)
    # 逐集写作只给一集的预算
    assert ContentGenerator._script_budget(3, episode_index=2) < ContentGenerator._script_budget(3)
# ── 逐集写作：合并而不是覆盖 ──────────────────────────────────────
def test_save_script_merges_episode_into_existing():
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "共三集短剧"}, headers=HEADERS).json()["id"]
    gen = ContentGenerator.__new__(ContentGenerator)
    gen.db = DB
    gen._save_script(pid, "共三集短剧", 1, json.dumps({
        "title": "三集剧",
        "episodes": [{"idx": 1, "title": "第一集", "tags": [], "script": "第一集正文"}],
    }, ensure_ascii=False))
    # 再写第 2 集：第 1 集必须还在
    payload = gen._save_script(pid, "共三集短剧", 1, json.dumps({
        "episodes": [{"idx": 2, "title": "第二集", "tags": [], "script": "第二集正文"}],
    }, ensure_ascii=False), episode_index=2)
    idxs = [e["idx"] for e in payload["episodes"]]
    assert idxs == [1, 2], idxs
    assert payload["title"] == "三集剧"
    assert payload["episodes"][0]["script"] == "第一集正文"
    with DB.read() as c:
        stored = json.loads(c.execute(
            "SELECT script_json FROM projects WHERE id=?", (pid,)
        ).fetchone()["script_json"])
    assert [e["idx"] for e in stored["episodes"]] == [1, 2]
# ── 端到端：流式逐集写作 ──────────────────────────────────────────
class _EchoTextProvider:
    """记录 prompt 的假 Provider：按 idx 返回对应的一集。"""
    def __init__(self):
        self.meta = ProviderMeta(id="echo_text", kind="openai_compat", source="proxy",
                                 abilities=("text",))
        self.prompts: list[tuple[str, str]] = []
    async def probe(self):
        from engine.app.adapters.base import ProbeResult
        return ProbeResult(ok=True, latency_ms=1, abilities=("text",))
    async def stream_chat(self, prompt, system, max_tokens=2048):
        self.prompts.append((prompt, system))
        # 从提示词里认出要写第几集
        import re
        m = re.search(r"第\s*(\d+)\s*集", prompt)
        idx = int(m.group(1)) if m else 1
        payload = json.dumps({
            "title": "测试剧",
            "episodes": [{"idx": idx, "title": f"第{idx}集", "tags": [], "script": f"第{idx}集的正文"}],
        }, ensure_ascii=False)
        for i in range(0, len(payload), 30):
            yield ("delta", payload[i:i + 30])
def _sse_done(text: str) -> dict:
    for block in text.split("\n\n"):
        ev = dt = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                dt = line[5:].strip()
        if ev == "done" and dt:
            return json.loads(dt)
    raise AssertionError(f"SSE 里没有 done 事件：{text[:300]}")
def test_stream_writes_episodes_one_by_one():
    """一集一集写：第 1 集写完再写第 2 集，第 1 集不能被覆盖。"""
    provider = _EchoTextProvider()
    REGISTRY.register(provider)
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "共三集短剧"}, headers=HEADERS).json()["id"]
    with client.stream("POST", f"/api/projects/{pid}/script/generate/stream",
                       headers=HEADERS, json={"version": 1}) as r:
        first = _sse_done("".join(r.iter_text()))
    assert [e["idx"] for e in first["episodes"]] == [1]
    with client.stream("POST", f"/api/projects/{pid}/script/generate/stream",
                       headers=HEADERS, json={"version": 1, "episode_index": 2}) as r:
        second = _sse_done("".join(r.iter_text()))
    idxs = [e["idx"] for e in second["episodes"]]
    assert idxs == [1, 2], idxs
    assert second["episodes"][0]["script"] == "第1集的正文"
    assert second["episodes"][1]["script"] == "第2集的正文"
    # 第二次请求的提示词必须说明只写第 2 集，并带上前情
    prompt, system = provider.prompts[-1]
    assert "第 2 集" in prompt and "第 2 集" in system
    assert "第 1 集" in prompt, "要带上前面已写好的剧情，保证连贯"
    assert "第1集的正文" in prompt
def test_stream_episode_index_beyond_target_is_rejected():
    """不能写出目标集数之外的集。"""
    REGISTRY.register(_EchoTextProvider())
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "只做一集"}, headers=HEADERS).json()["id"]
    with client.stream("POST", f"/api/projects/{pid}/script/generate/stream",
                       headers=HEADERS, json={"version": 1, "episode_index": 3}) as r:
        text = "".join(r.iter_text())
    assert "event: error" in text, "超出目标集数必须明确拒绝"
