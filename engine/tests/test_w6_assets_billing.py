"""W6 测试：素材落地本机 + 按来源计费（2026-11-21 修复）。"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["MANGJU_DATA_DIR"] = tempfile.mkdtemp(prefix="mangju-test-w6-")

import pytest
from fastapi.testclient import TestClient

from engine.app.main import app, DB, LOCAL_TOKEN, REGISTRY, ASSETS
from engine.app.adapters.base import GenResult, ImageGenRequest, ProviderMeta, VideoGenRequest
from engine.app.storage.util import ulid
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


class _LocalImageProvider:
    """返回本机 HTTP 图片地址的假 Provider（不接触真实厂商）。"""

    def __init__(self, url: str, source: str = "owned"):
        self.meta = ProviderMeta(id="test_image", kind="openai_compat", source=source,
                                 abilities=("image",))
        self.url = url

    async def probe(self):
        from engine.app.adapters.base import ProbeResult
        return ProbeResult(ok=True)

    async def submit(self, req: object) -> str:
        self.last = req
        return "img_task"

    async def poll(self, task_id: str) -> GenResult:
        return GenResult(ok=True, asset_ref=self.url, units_used=1.0)


class _LocalVideoProvider:
    """自带密钥来源的视频 Provider：成功即返回视频地址。"""

    def __init__(self, source: str = "owned"):
        self.meta = ProviderMeta(id="test_video", kind="openai_compat", source=source,
                                 abilities=("video",))

    async def probe(self):
        from engine.app.adapters.base import ProbeResult
        return ProbeResult(ok=True)

    async def submit(self, req: object) -> str:
        return "vid_task"

    async def poll(self, task_id: str) -> GenResult:
        return GenResult(ok=True, asset_ref="https://example.invalid/v.mp4",
                         units_used=5.0, raw_cost_estimate=9.0)


# ---------- 本地 HTTP 图片服务 ----------

class _ImgHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PNG_1x1)))
        self.end_headers()
        self.wfile.write(PNG_1x1)

    def log_message(self, *args):  # 静音
        return


@pytest.fixture(scope="module")
def img_server():
    srv = HTTPServer(("127.0.0.1", 0), _ImgHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}/pic.png"
    srv.shutdown()


# ---------- 素材落地 ----------

def _new_project(idea: str) -> str:
    client = TestClient(app)
    return client.post("/api/projects", json={"idea": idea}, headers=HEADERS).json()["id"]


def test_asset_store_saves_remote_file_locally(img_server):
    """厂商图片链接必须落盘到本机并登记 assets 表（链接会过期，不能只存链接）。"""
    pid = _new_project("素材落地测试三集竖屏短剧")
    row = ASSETS.save_remote(pid, "image", img_server)
    assert row is not None
    assert row["size_bytes"] == len(PNG_1x1)
    p = ASSETS.resolve(row["local_path"])
    assert p.exists() and p.read_bytes() == PNG_1x1
    # 落盘路径必须相对数据目录（数据目录可迁移）
    assert not os.path.isabs(row["local_path"])
    with DB.read() as c:
        got = c.execute("SELECT * FROM assets WHERE id=?", (row["id"],)).fetchone()
    assert got is not None and got["project_id"] == pid


def test_asset_store_saves_base64_data_url():
    """厂商直接返回 base64 时也要落成真实文件。"""
    pid = _new_project("base64 素材测试三集竖屏短剧")
    url = "data:image/png;base64," + base64.b64encode(PNG_1x1).decode()
    row = ASSETS.save_remote(pid, "image", url)
    assert row is not None
    assert ASSETS.resolve(row["local_path"]).exists()


def test_asset_file_endpoint_serves_relative_path(img_server):
    """素材端点必须按数据目录解析相对路径（否则文件存在也报 404）。"""
    client = TestClient(app)
    pid = _new_project("素材端点测试三集竖屏短剧")
    row = ASSETS.save_remote(pid, "image", img_server)
    r = client.get(f"/api/assets/{row['id']}/file?token={LOCAL_TOKEN}")
    assert r.status_code == 200
    assert r.content == PNG_1x1


def test_character_ref_is_localized_to_engine_url(img_server):
    """定妆图生成后要指向引擎本机地址，且库里带 asset_id。"""
    REGISTRY.register(_LocalImageProvider(img_server))
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "定妆图落地测试三集竖屏短剧"},
                      headers=HEADERS).json()["id"]
    r = client.post(f"/api/projects/{pid}/characters/generate", json={"count": 2}, headers=HEADERS)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 2
    assert items[0]["ref_url"].startswith("http://testserver/api/assets/")
    with DB.read() as c:
        row = c.execute("SELECT ref_images FROM characters WHERE id=?",
                        (items[0]["id"],)).fetchone()
    refs = json.loads(row["ref_images"])
    assert refs[0]["asset_id"] and refs[0]["url"].startswith("assets/")
    # 项目详情里的定妆图同样是可直接显示的绝对地址
    d = client.get(f"/api/projects/{pid}", headers=HEADERS).json()
    assert d["characters"][0]["ref_url"].startswith("http://testserver/api/assets/")


def test_project_detail_backfills_old_remote_refs(img_server):
    """旧项目里存的是厂商链接：打开项目时要自动取回本机（链接过期也不丢画面）。"""
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "旧定妆图自愈测试三集竖屏短剧"},
                      headers=HEADERS).json()["id"]
    cid = f"chr_{pid}_1"
    with DB.tx() as c:
        c.execute("INSERT OR REPLACE INTO characters(id,project_id,name,desc_text,ref_images,locked) "
                  "VALUES(?,?,?,?,?,0)",
                  (cid, pid, "角色 1", "旧角色",
                   json.dumps([{"url": img_server, "rank": 1}], ensure_ascii=False)))
    d = client.get(f"/api/projects/{pid}", headers=HEADERS).json()
    assert d["characters"][0]["ref_url"].startswith("http://testserver/api/assets/")


# ---------- 按来源计费 ----------

def test_own_key_generation_records_usage_only():
    """纯开源版：生成走自己的厂商账号，本地只记用量事件，无平台扣费。"""
    REGISTRY.register(_LocalVideoProvider(source="owned"))
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "自有密钥计费测试三集竖屏短剧"},
                      headers=HEADERS).json()["id"]
    r = client.post(f"/api/projects/{pid}/generation/start", json={"shot_count": 2, "ability": "video"}, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["billing"] == "own_key"
    import time
    for _ in range(60):
        p = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS).json()
        if p and p.get("finished"):
            break
        time.sleep(0.1)
    with DB.read() as c:
        spent = c.execute("SELECT COALESCE(SUM(credits_spent),0) FROM usage_events").fetchone()[0]
        n = c.execute("SELECT COUNT(*) FROM usage_events WHERE ok=1").fetchone()[0]
    assert spent == 0, "纯开源版没有任何平台扣费"
    assert n >= 2, "用量事件仍然要逐条记录"


class _UnsupportedVideoProvider:
    """厂商根本没有视频端点（把图片模型填进视频槽就是这种）：提交直接 404。"""

    def __init__(self, source: str = "owned"):
        self.meta = ProviderMeta(id="test_video", kind="openai_compat", source=source,
                                 abilities=("video",))
        self.calls = 0

    async def probe(self):
        from engine.app.adapters.base import ProbeResult
        return ProbeResult(ok=True)

    async def submit(self, req: object) -> str:
        self.calls += 1
        raise RuntimeError("provider_error: HTTP 404: not found")

    async def poll(self, task_id: str) -> GenResult:
        return GenResult(ok=False, fail_reason="unknown")


class _CapturingImageProvider:
    """记录收到提示词的图片 Provider：验证画面用的是真实分镜表。"""

    def __init__(self, source: str = "owned"):
        self.meta = ProviderMeta(id="test_image", kind="openai_compat", source=source,
                                 abilities=("image",))
        self.prompts: list[str] = []

    async def probe(self):
        from engine.app.adapters.base import ProbeResult
        return ProbeResult(ok=True)

    async def submit(self, req: object) -> str:
        self.prompts.append(req.prompt)
        return "img_task"

    async def poll(self, task_id: str) -> GenResult:
        return GenResult(ok=True, asset_ref="https://example.invalid/a.png", units_used=1.0)


def test_step6_generates_frames_with_image_model_and_real_shots():
    """第 6 步「生成画面」用图片模型，且场景必须来自用户第 5 步确认的真实分镜表。"""
    provider = _CapturingImageProvider(source="owned")
    REGISTRY.register(provider)
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "画面生成真实分镜测试三集竖屏短剧"},
                      headers=HEADERS).json()["id"]
    # 用户第 5 步确认过的分镜表
    shots = {"shots": [{"idx": 1, "scene": "雨夜便利店门口，男孩攥着零钱", "importance": "key"},
                       {"idx": 2, "scene": "公交车最后一排，母亲别过脸", "importance": "transition"}]}
    with DB.tx() as c:
        c.execute("UPDATE projects SET shots_json=? WHERE id=?",
                  (json.dumps(shots, ensure_ascii=False), pid))
    r = client.post(f"/api/projects/{pid}/generation/start",
                    json={"shot_count": 2}, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["ability"] == "image"
    import time
    for _ in range(60):
        p = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS).json()
        if p and p.get("done", 0) >= 2:
            break
        time.sleep(0.1)
    assert provider.prompts, "图片模型没有被调用"
    assert "雨夜便利店门口" in provider.prompts[0], "画面提示词必须来自真实分镜表"


def test_generation_falls_back_to_video_when_no_image_provider():
    """没配图片模型但配了视频模型时，第 6 步降级用视频模型出画面，流程不中断。"""
    REGISTRY.register(_LocalVideoProvider(source="owned"))
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "画面能力降级测试三集竖屏短剧"},
                      headers=HEADERS).json()["id"]
    r = client.post(f"/api/projects/{pid}/generation/start",
                    json={"shot_count": 2}, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["ability"] == "video"


def test_unsupported_capability_stops_batch_immediately():
    """厂商不支持该能力时：立刻停批并说清楚，不把 12 个镜头逐个撞墙。"""
    provider = _UnsupportedVideoProvider(source="owned")
    REGISTRY.register(provider)
    client = TestClient(app)
    pid = client.post("/api/projects", json={"idea": "能力不支持快速停批测试三集竖屏短剧"},
                      headers=HEADERS).json()["id"]
    r = client.post(f"/api/projects/{pid}/generation/start", json={"shot_count": 12, "ability": "video"}, headers=HEADERS)
    assert r.status_code == 200, r.text
    import time
    prog = {}
    for _ in range(80):
        prog = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS).json()
        if prog.get("fatal_reason"):
            break
        time.sleep(0.1)
    assert prog.get("fatal_reason"), prog
    assert "不支持" in prog["fatal_reason"]
    # 只提交了一次：没有把 12 个镜头全部撞一遍
    assert provider.calls == 1, f"不应逐个镜头重试，实际提交 {provider.calls} 次"
