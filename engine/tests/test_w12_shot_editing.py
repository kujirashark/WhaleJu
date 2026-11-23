"""W12：分镜可以单独编辑、调整、增删。
用户要求："分镜应该也可以单独编辑。可以调整。"
覆盖：
- 单镜编辑：改场景描述 / 改重要度 / 调整顺序
- 新增镜头 / 删除镜头（删除连带清掉该镜已生成的画面）
- 编辑后重生成这一镜，用的是**改过的**描述
- 稳定 key：重排/删除后，素材关联不串台
- 老数据（没有 key）仍可编辑
"""
from __future__ import annotations
import base64
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
os.environ["MANGJU_DATA_DIR"] = tempfile.mkdtemp(prefix="mangju-test-w12-")
import pytest
from fastapi.testclient import TestClient
from engine.app.main import app, DB, LOCAL_TOKEN, REGISTRY, ASSETS
from engine.app.adapters.base import GenResult, ImageGenRequest, ProviderMeta
from engine.app.workflow.generation import db_shot_id
from engine.tests.conftest import truncate_all
HEADERS = {"X-Local-Token": LOCAL_TOKEN}
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
@pytest.fixture(autouse=True)
def clean_db():
    DB.init_schema()
    truncate_all(DB)
    REGISTRY.clear()
class _ImgHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PNG_1x1)))
        self.end_headers()
        self.wfile.write(PNG_1x1)
    def log_message(self, *a):  # noqa: D401
        pass
@pytest.fixture(scope="module")
def img_server():
    srv = HTTPServer(("127.0.0.1", 0), _ImgHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/x.png"
    srv.shutdown()
class _LocalImageProvider:
    def __init__(self, url: str):
        self.meta = ProviderMeta(id="w12_image", kind="openai_compat", source="owned",
                                 abilities=("image",))
        self.url = url
        self.calls = 0
        self.prompts: list[str] = []
    async def probe(self):
        from engine.app.adapters.base import ProbeResult
        return ProbeResult(ok=True)
    async def submit(self, req: object) -> str:
        self.calls += 1
        self.prompts.append(getattr(req, "prompt", ""))
        return f"img_task_{self.calls}"
    async def poll(self, task_id: str) -> GenResult:
        return GenResult(ok=True, asset_ref=self.url, units_used=1.0)
def _make_project(idea: str = "只做一集") -> str:
    client = TestClient(app)
    return client.post("/api/projects", json={"idea": idea}, headers=HEADERS).json()["id"]
def _set_plan(pid: str, shots: list[dict]) -> None:
    """直接写入分镜表（模拟模型拆镜头的结果）。"""
    payload = {"shots": shots, "partial": False}
    DB.execute(
        "UPDATE projects SET shots_json=? WHERE id=?",
        (json.dumps(payload, ensure_ascii=False), pid),
    )
def _plan_of(pid: str) -> list[dict]:
    with DB.read() as c:
        row = c.execute("SELECT shots_json FROM projects WHERE id=?", (pid,)).fetchone()
    return json.loads(row["shots_json"]).get("shots") or []
# ── 单镜编辑 ────────────────────────────────────────────────────────
def test_edit_single_shot_scene():
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [
        {"key": "sh_a", "idx": 1, "scene": "第一镜：猫咖门口", "importance": "key"},
        {"key": "sh_b", "idx": 2, "scene": "第二镜：面试桌", "importance": "transition"},
    ])
    r = client.put(f"/api/projects/{pid}/shots/sh_a", headers=HEADERS,
                   json={"scene": "第一镜改成：雨天巷口"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["changed"] is True
    shots = body["shots"]
    assert shots[0]["scene"] == "第一镜改成：雨天巷口"
    assert shots[0]["key"] == "sh_a", "key 不能变（素材靠它关联）"
    # 别的镜头不受影响
    assert shots[1]["scene"] == "第二镜：面试桌"
    # 落库了
    assert _plan_of(pid)[0]["scene"] == "第一镜改成：雨天巷口"
def test_edit_shot_importance():
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [{"key": "sh_a", "idx": 1, "scene": "某镜", "importance": "transition"}])
    r = client.put(f"/api/projects/{pid}/shots/sh_a", headers=HEADERS,
                   json={"importance": "key"})
    assert r.status_code == 200
    assert r.json()["shots"][0]["importance"] == "key"
def test_edit_shot_reorder():
    """调整顺序：镜头内容跟着 key 走，序号重新排列。"""
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [
        {"key": "sh_a", "idx": 1, "scene": "A", "importance": "key"},
        {"key": "sh_b", "idx": 2, "scene": "B", "importance": "transition"},
        {"key": "sh_c", "idx": 3, "scene": "C", "importance": "transition"},
    ])
    r = client.put(f"/api/projects/{pid}/shots/sh_c", headers=HEADERS, json={"idx": 1})
    assert r.status_code == 200, r.text
    shots = r.json()["shots"]
    assert [s["scene"] for s in shots] == ["C", "A", "B"]
    assert [s["idx"] for s in shots] == [1, 2, 3]
    # key 仍跟着内容
    assert shots[0]["key"] == "sh_c"
def test_edit_unknown_shot_rejected():
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [{"key": "sh_a", "idx": 1, "scene": "A"}])
    r = client.put(f"/api/projects/{pid}/shots/nope", headers=HEADERS, json={"scene": "X"})
    assert r.status_code == 404
    assert "找不到这个镜头" in r.text
def test_empty_scene_rejected():
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [{"key": "sh_a", "idx": 1, "scene": "A"}])
    r = client.put(f"/api/projects/{pid}/shots/sh_a", headers=HEADERS, json={"scene": "   "})
    assert r.status_code == 400
    assert "不能为空" in r.text
# ── 增删 ────────────────────────────────────────────────────────────
def test_add_shot():
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [{"key": "sh_a", "idx": 1, "scene": "A"}])
    r = client.post(f"/api/projects/{pid}/shots", headers=HEADERS,
                    json={"scene": "新增的一镜：收尾空镜"})
    assert r.status_code == 200, r.text
    shots = r.json()["shots"]
    assert len(shots) == 2
    assert shots[1]["scene"] == "新增的一镜：收尾空镜"
    assert shots[1]["key"] != "sh_a"
    assert _plan_of(pid)[1]["scene"] == "新增的一镜：收尾空镜"
def test_delete_shot_removes_its_media():
    """删镜头要连带清掉它已生成的画面（否则导出会多出一段）。"""
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [
        {"key": "sh_a", "idx": 1, "scene": "A"},
        {"key": "sh_b", "idx": 2, "scene": "B"},
    ])
    # 先编辑一次触发分镜表 → shots 表同步（素材外键指向 shots.id）
    client.put(f"/api/projects/{pid}/shots/sh_b", headers=HEADERS, json={"scene": "B（已同步）"})
    # 给 sh_a 造一张素材
    ap = ASSETS.data_dir / "assets" / pid / "a.png"
    ap.parent.mkdir(parents=True, exist_ok=True)
    ap.write_bytes(PNG_1x1)
    DB.insert("assets", {
        "id": "as_del_a", "project_id": pid, "kind": "shot",
        "local_path": ASSETS.rel_path(ap), "sha256": "x", "size_bytes": len(PNG_1x1),
        "shot_id": db_shot_id(pid, "sh_a"),
    })
    r = client.delete(f"/api/projects/{pid}/shots/sh_a", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert [s["key"] for s in r.json()["shots"]] == ["sh_b"]
    # 素材与文件都要清掉
    with DB.read() as c:
        n = c.execute("SELECT COUNT(*) FROM assets WHERE id='as_del_a'").fetchone()[0]
    assert n == 0, "删镜头后素材记录还在"
    assert not ap.exists(), "删镜头后本机文件还在"
def test_delete_shot_keeps_other_media(img_server):
    """删第 1 镜，第 2 镜的素材必须原样保留（key 稳定，关联不串台）。"""
    REGISTRY.register(_LocalImageProvider(img_server))
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [
        {"key": "sh_a", "idx": 1, "scene": "A"},
        {"key": "sh_b", "idx": 2, "scene": "B"},
    ])
    client.post(f"/api/projects/{pid}/generation/start", headers=HEADERS, json={"shot_count": 2})
    import time
    t0 = time.time()
    while time.time() - t0 < 20:
        pr = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS).json()
        if pr.get("total") and pr.get("done", 0) >= pr.get("total", 0):
            break
        time.sleep(0.2)
    with DB.read() as c:
        before = c.execute(
            "SELECT shot_id FROM assets WHERE project_id=? AND shot_id IS NOT NULL", (pid,)
        ).fetchall()
    assert len(before) == 2, [dict(r) for r in before]
    keep = [r["shot_id"] for r in before if r["shot_id"].endswith("sh_b")]
    assert keep, [dict(r) for r in before]
    r = client.delete(f"/api/projects/{pid}/shots/sh_a", headers=HEADERS)
    assert r.status_code == 200, r.text
    with DB.read() as c:
        after = c.execute(
            "SELECT shot_id FROM assets WHERE project_id=? AND shot_id IS NOT NULL", (pid,)
        ).fetchall()
    ids = [r["shot_id"] for r in after]
    assert keep[0] in ids, "别的镜头的素材被误删了"
    assert len(ids) == 1, ids
# ── 编辑后重生成：用改过的描述 ────────────────────────────────────────
def test_regenerate_uses_edited_scene(img_server):
    """编辑了分镜，重生成这一镜必须用新描述（否则等于白改）。"""
    provider = _LocalImageProvider(img_server)
    REGISTRY.register(provider)
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [
        {"key": "sh_a", "idx": 1, "scene": "原始描述：猫咖门口"},
        {"key": "sh_b", "idx": 2, "scene": "第二镜"},
    ])
    client.post(f"/api/projects/{pid}/generation/start", headers=HEADERS, json={"shot_count": 2})
    import time
    t0 = time.time()
    while time.time() - t0 < 20:
        pr = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS).json()
        if pr.get("total") and pr.get("done", 0) >= pr.get("total", 0):
            break
        time.sleep(0.2)
    # 改第 1 镜的描述
    client.put(f"/api/projects/{pid}/shots/sh_a", headers=HEADERS,
               json={"scene": "改过的描述：雨夜天台"})
    provider.prompts.clear()
    r = client.post(f"/api/projects/{pid}/shots/sh_a/regenerate", headers=HEADERS, json={})
    assert r.status_code == 200, r.text
    assert provider.prompts, "重生成没有调用厂商"
    assert any("雨夜天台" in p for p in provider.prompts), \
        f"重生成用的还是旧描述：{provider.prompts}"
def test_stale_shots_reported_when_edited(img_server):
    """已经出过画面的镜头改了描述 → 要告诉用户"需要重新生成这一镜"。"""
    REGISTRY.register(_LocalImageProvider(img_server))
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [{"key": "sh_a", "idx": 1, "scene": "原始描述"}])
    client.post(f"/api/projects/{pid}/generation/start", headers=HEADERS, json={"shot_count": 1})
    import time
    t0 = time.time()
    while time.time() - t0 < 20:
        pr = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS).json()
        if pr.get("total") and pr.get("done", 0) >= pr.get("total", 0):
            break
        time.sleep(0.2)
    r = client.put(f"/api/projects/{pid}/shots/sh_a", headers=HEADERS, json={"scene": "新描述"})
    assert r.status_code == 200, r.text
    assert "sh_a" in r.json()["stale_shots"], r.json()
def test_stale_marker_persists_in_shots_media(img_server):
    """改了描述 → 标记落库（shots.status='edited'），刷新页面后仍在。"""
    REGISTRY.register(_LocalImageProvider(img_server))
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [{"key": "sh_a", "idx": 1, "scene": "原始描述"}])
    client.post(f"/api/projects/{pid}/generation/start", headers=HEADERS, json={"shot_count": 1})
    import time
    t0 = time.time()
    while time.time() - t0 < 20:
        pr = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS).json()
        if pr.get("total") and pr.get("done", 0) >= pr.get("total", 0):
            break
        time.sleep(0.2)
    client.put(f"/api/projects/{pid}/shots/sh_a", headers=HEADERS, json={"scene": "新描述"})
    # 从库里读：状态应该是 edited（待重生成）
    media = client.get(f"/api/projects/{pid}/shots/media", headers=HEADERS).json()
    item = next(i for i in media["items"] if i["shot_id"] == "sh_a")
    assert item["status"] == "edited", item
    # 画面还在（没被删），只是提示需要重生成
    assert item["media_url"], item
def test_legacy_media_without_shot_id_still_marked_stale(img_server):
    """老项目的素材没写 shot_id：改描述也要提示"待重生成"。"""
    REGISTRY.register(_LocalImageProvider(img_server))
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [{"key": "s1", "idx": 1, "scene": "原始描述"}])
    client.post(f"/api/projects/{pid}/generation/start", headers=HEADERS, json={"shot_count": 1})
    import time
    t0 = time.time()
    while time.time() - t0 < 20:
        pr = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS).json()
        if pr.get("total") and pr.get("done", 0) >= pr.get("total", 0):
            break
        time.sleep(0.2)
    # 模拟老数据：清掉精确关联
    with DB.tx() as c:
        c.execute("UPDATE assets SET shot_id=NULL WHERE project_id=?", (pid,))
    r = client.put(f"/api/projects/{pid}/shots/s1", headers=HEADERS, json={"scene": "改过的描述"})
    assert r.status_code == 200, r.text
    assert "s1" in r.json()["stale_shots"], r.json()
# ── 老数据兼容 ──────────────────────────────────────────────────────
def test_legacy_plan_without_key_is_editable():
    """老项目的分镜表没有 key（用序号），也要能编辑。"""
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [{"idx": 1, "scene": "老的第一镜", "importance": "key"}])
    r = client.put(f"/api/projects/{pid}/shots/s1", headers=HEADERS, json={"scene": "老的第一镜改好了"})
    assert r.status_code == 200, r.text
    assert r.json()["shots"][0]["scene"] == "老的第一镜改好了"
    assert r.json()["shots"][0]["key"] == "s1"
def test_shots_media_uses_plan_keys():
    """镜头清单按分镜表的 key 关联素材。"""
    client = TestClient(app)
    pid = _make_project()
    _set_plan(pid, [
        {"key": "sh_x", "idx": 1, "scene": "镜头X", "importance": "key"},
        {"key": "sh_y", "idx": 2, "scene": "镜头Y", "importance": "transition"},
    ])
    r = client.get(f"/api/projects/{pid}/shots/media", headers=HEADERS).json()
    assert r["total"] == 2
    assert [i["shot_id"] for i in r["items"]] == ["sh_x", "sh_y"]
    assert r["items"][0]["scene_desc"] == "镜头X"
