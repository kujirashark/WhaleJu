"""W11：所见即所得 —— 状态一致 + 镜头素材持久化 + 媒体可预览。

用户反馈的三个问题：
1. AI 生成标识不需要放进画面；
2. 同一屏两套说法：中间卡片写"已确认"，右侧角色列表写"待确认"；
3. 第 6/7 步看不到画面（引擎重启后更是一片空白），图和视频不能直接预览播放。

覆盖：
- 角色锁定状态落到库里，刷新后仍然一致（引擎事实，不是前端内存态）
- 镜头素材清单从库里还原（引擎重启后仍能显示画面）
- 素材文件端点支持 Range（视频能拖进度条）
- shots.id 带项目前缀（多项目不再互相覆盖）
- 画面里不再烧 AI 标识
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["MANGJU_DATA_DIR"] = tempfile.mkdtemp(prefix="mangju-test-w11-")

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
        self.meta = ProviderMeta(id="w11_image", kind="openai_compat", source="owned",
                                 abilities=("image",))
        self.url = url
        self.calls = 0

    async def probe(self):
        from engine.app.adapters.base import ProbeResult
        return ProbeResult(ok=True)

    async def submit(self, req: object) -> str:
        self.calls += 1
        return f"img_task_{self.calls}"

    async def poll(self, task_id: str) -> GenResult:
        return GenResult(ok=True, asset_ref=self.url, units_used=1.0)


def _make_project(idea: str = "只做一集") -> str:
    client = TestClient(app)
    return client.post("/api/projects", json={"idea": idea}, headers=HEADERS).json()["id"]


def _wait_batch(pid: str, timeout: float = 30.0):
    import time
    client = TestClient(app)
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS).json()
        if r.get("total") and r.get("done", 0) >= r.get("total", 0):
            return r
        time.sleep(0.2)
    raise AssertionError("生成批次没有在超时内完成")


# ── 1. 角色锁定：引擎事实，刷新后一致 ────────────────────────────────

def test_role_lock_is_persisted_in_db():
    """确认角色形象后，锁定状态必须落库 —— 刷新页面不能变回"待确认"。"""
    client = TestClient(app)
    pid = _make_project()
    DB.insert("characters", {
        "id": f"chr_{pid}_1", "project_id": pid, "name": "角色 1",
        "desc_text": "橘猫", "ref_images": json.dumps([]), "locked": 0,
    })
    # 未确认时：引擎说没锁
    r = client.get(f"/api/projects/{pid}/shots/roles-lock", headers=HEADERS).json()
    assert r["locked"] is False

    r = client.post(f"/api/projects/{pid}/shots/roles-lock", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["locked"] == 1

    # 再读一次（模拟刷新页面）：仍然是已锁定
    r = client.get(f"/api/projects/{pid}/shots/roles-lock", headers=HEADERS).json()
    assert r["locked"] is True

    # 项目详情里也带同一个事实
    detail = client.get(f"/api/projects/{pid}", headers=HEADERS).json()
    assert detail["roles_locked"] is True
    assert all(int(c["locked"]) == 1 for c in detail["characters"])


def test_role_lock_rejected_without_characters():
    client = TestClient(app)
    pid = _make_project()
    r = client.post(f"/api/projects/{pid}/shots/roles-lock", headers=HEADERS)
    assert r.status_code == 400
    assert "定妆图" in r.text


def test_advance_step4_marks_characters_locked():
    """走状态机确认（第 4 步）也要把角色标记为已锁定。"""
    client = TestClient(app)
    pid = _make_project()
    DB.insert("characters", {
        "id": f"chr_{pid}_1", "project_id": pid, "name": "角色 1",
        "desc_text": "橘猫", "ref_images": json.dumps([]), "locked": 0,
    })
    # 推进到 CP2_PENDING
    DB.execute("UPDATE projects SET status='CP2_PENDING' WHERE id=?", (pid,))
    r = client.post(f"/api/projects/{pid}/steps/4/advance", headers=HEADERS,
                    json={"action": "approve", "payload": {"selected": [f"chr_{pid}_1"]}})
    assert r.status_code == 200, r.text
    assert "lock_characters" in r.json()["effects"]

    with DB.read() as c:
        row = c.execute("SELECT locked FROM characters WHERE project_id=?", (pid,)).fetchone()
    assert int(row["locked"]) == 1, "确认角色后必须落库锁定状态"


# ── 2. 镜头素材持久化：引擎重启后仍能看到画面 ──────────────────────────

def test_shots_media_restores_from_db(img_server):
    """素材落库后，即使内存批次没了，也能从库里还原出镜头清单和画面地址。"""
    REGISTRY.register(_LocalImageProvider(img_server))
    pid = _make_project()
    client = TestClient(app)
    client.post(f"/api/projects/{pid}/generation/start", headers=HEADERS, json={"shot_count": 2})
    _wait_batch(pid)

    r = client.get(f"/api/projects/{pid}/shots/media", headers=HEADERS).json()
    assert r["total"] == 2, r
    for it in r["items"]:
        assert it["status"] == "done", it
        assert it["media_url"], it
        # 地址能真的取到图片字节
        assert client.get(it["media_url"]).status_code == 200


def test_progress_restores_from_db_when_batch_gone(img_server):
    """引擎重启（内存批次丢失）后，progress 不能报"未开始"让用户以为白干了。"""
    REGISTRY.register(_LocalImageProvider(img_server))
    pid = _make_project()
    client = TestClient(app)
    client.post(f"/api/projects/{pid}/generation/start", headers=HEADERS, json={"shot_count": 2})
    _wait_batch(pid)

    # 模拟引擎重启：清掉内存批次
    from engine.app.main import GENERATIONS
    GENERATIONS.batches.clear()
    GENERATIONS.by_project.clear()

    r = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS).json()
    assert r["total"] == 2, r
    assert r["done"] == 2, r
    assert r["restored_from_db"] is True
    for it in r["items"]:
        assert it["media_url"], it
        assert client.get(it["media_url"]).status_code == 200


# ── 3. 媒体可预览：Range ─────────────────────────────────────────────

def test_asset_file_supports_range():
    """视频要能在页面里拖进度条 —— 素材端点必须支持 Range。"""
    client = TestClient(app)
    pid = _make_project()
    aid = "as_range_test"
    p = ASSETS.data_dir / "assets" / pid / f"{aid}.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"0" * 1000)
    DB.insert("assets", {
        "id": aid, "project_id": pid, "kind": "video",
        "local_path": ASSETS.rel_path(p), "sha256": "x", "size_bytes": 1000,
    })

    r = client.get(f"/api/assets/{aid}/file?token={LOCAL_TOKEN}")
    assert r.status_code == 200
    assert r.headers.get("accept-ranges") == "bytes"
    assert r.headers.get("content-type", "").startswith("video/")

    r = client.get(f"/api/assets/{aid}/file?token={LOCAL_TOKEN}",
                   headers={"Range": "bytes=0-99"})
    assert r.status_code == 206, r.status_code
    assert r.headers.get("content-range") == "bytes 0-99/1000"
    assert len(r.content) == 100


# ── 4. shots.id 跨项目隔离 ───────────────────────────────────────────

def test_db_shot_id_is_project_scoped():
    """shots.id 是全局主键：必须带项目前缀，否则项目 A 的 s1 会覆盖项目 B 的 s1。"""
    a = db_shot_id("projA", "s1")
    b = db_shot_id("projB", "s1")
    assert a != b
    assert a.endswith("s1") and b.endswith("s1")
    # 幂等：已经带前缀的不再叠加
    assert db_shot_id("projA", a) == a


def test_shot_rows_do_not_collide_across_projects(img_server):
    """两个项目各生成 1 镜：shots 表里必须是两行，不能互相覆盖。"""
    REGISTRY.register(_LocalImageProvider(img_server))
    client = TestClient(app)
    p1 = _make_project("项目甲")
    p2 = _make_project("项目乙")
    client.post(f"/api/projects/{p1}/generation/start", headers=HEADERS, json={"shot_count": 1})
    _wait_batch(p1)
    client.post(f"/api/projects/{p2}/generation/start", headers=HEADERS, json={"shot_count": 1})
    _wait_batch(p2)

    with DB.read() as c:
        rows = c.execute("SELECT id FROM shots").fetchall()
    ids = {r["id"] for r in rows}
    assert len(ids) == 2, f"两个项目的镜头被合并了：{ids}"


# ── 5. 画面里不再烧 AI 标识 ─────────────────────────────────────────

def test_compose_does_not_burn_watermark_into_frame():
    """用户明确要求：AI 生成标识不放在画面里。

    检测的是真正会烧字的那两处（compose / compose_slides 的 ffmpeg 命令），
    而不是全文搜索 —— 注释里提到某个滤镜名不算真烧了。
    """
    import re
    from pathlib import Path
    src = (Path(__file__).parents[2] / "engine" / "app" / "publish" / "kit.py").read_text(encoding="utf-8")
    # 真正会烧字的是 drawtext 滤镜；出现即视为违规
    burns = re.findall(r"drawtext\s*=", src)
    assert not burns, f"成片合成里还在烧 AI 标识进画面：{burns}"
    # 但声明内容仍然保留在常量与发布文案里
    from engine.app.publish.kit import AI_DECLARATION
    assert "AI 生成" in AI_DECLARATION


# ── 6. 成片状态持久化：刷新页面后第 8 步还能看到并播放 ───────────────

def test_latest_work_is_returned_by_project_detail():
    """导出过的成片必须能从项目详情读回 —— 刷新页面后第 8 步不能变空白。"""
    client = TestClient(app)
    pid = _make_project()
    work_id = "wk_detail_test"
    p = ASSETS.data_dir / "works" / f"{work_id}.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"0" * 2048)
    DB.insert("assets", {
        "id": work_id, "project_id": pid, "kind": "work",
        "local_path": ASSETS.rel_path(p), "sha256": "x", "size_bytes": 2048,
    })

    detail = client.get(f"/api/projects/{pid}", headers=HEADERS).json()
    w = detail.get("latest_work")
    assert w, "项目详情必须带回最新成片"
    assert w["work_id"] == work_id
    assert w["format"] == "mp4"
    assert w["size_bytes"] == 2048
    # 预览地址可用（支持拖进度条）
    assert w["preview_url"].startswith("/api/works/")
    assert client.get(w["preview_url"]).status_code == 200


def test_no_work_means_no_latest_work():
    client = TestClient(app)
    pid = _make_project()
    detail = client.get(f"/api/projects/{pid}", headers=HEADERS).json()
    assert detail.get("latest_work") is None


def test_role_lock_backfill_fixes_legacy_projects():
    """老项目：状态已过 CP2_PENDING（用户确认过）但 locked 从没写过 → 启动时回填。"""
    from engine.app.main import _sync_role_locks
    client = TestClient(app)
    pid = _make_project()
    DB.insert("characters", {
        "id": f"chr_{pid}_1", "project_id": pid, "name": "角色 1",
        "desc_text": "橘猫", "ref_images": json.dumps([]), "locked": 0,
    })
    # 项目已走到 DELIVER：说明角色形象当时是确认过的
    DB.execute("UPDATE projects SET status='DELIVER' WHERE id=?", (pid,))

    _sync_role_locks()

    with DB.read() as c:
        row = c.execute("SELECT locked FROM characters WHERE project_id=?", (pid,)).fetchone()
    assert int(row["locked"]) == 1, "老项目的角色锁定状态应被回填"


def test_role_lock_backfill_skips_unconfirmed_projects():
    """还在 CP2_PENDING（用户没确认）的项目不能被回填成已确认。"""
    from engine.app.main import _sync_role_locks
    client = TestClient(app)
    pid = _make_project()
    DB.insert("characters", {
        "id": f"chr_{pid}_1", "project_id": pid, "name": "角色 1",
        "desc_text": "橘猫", "ref_images": json.dumps([]), "locked": 0,
    })
    DB.execute("UPDATE projects SET status='CP2_PENDING' WHERE id=?", (pid,))

    _sync_role_locks()

    with DB.read() as c:
        row = c.execute("SELECT locked FROM characters WHERE project_id=?", (pid,)).fetchone()
    assert int(row["locked"]) == 0, "还没确认角色的项目不该被标记为已确认"
