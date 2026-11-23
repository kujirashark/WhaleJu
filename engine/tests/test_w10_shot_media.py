"""W10：镜头素材可看可重生成 + 成片在线预览。
用户要求：
1. 第 6 步要看得见每个镜头的真实画面（图片/视频），不能只有一行状态文字；
2. 不满意的镜头能单独重新生成（不能整批重跑，那等于白烧一轮额度）；
3. 导出成片后马上能在页面里看，不用先下载。
覆盖：
- progress 事件带 media_url（指向本机素材，永久有效）
- 单镜头重新生成：成功换新素材、旧素材作废（导出不会把新旧都拼进去）
- 越界/不存在的镜头明确拒绝
- 成片 preview 支持 Range（浏览器才能拖进度条）
"""
from __future__ import annotations
import base64
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
os.environ["MANGJU_DATA_DIR"] = tempfile.mkdtemp(prefix="mangju-test-w10-")
import pytest
from fastapi.testclient import TestClient
from engine.app.main import app, DB, LOCAL_TOKEN, REGISTRY, ASSETS
from engine.app.adapters.base import GenResult, ImageGenRequest, ProviderMeta
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
        self.meta = ProviderMeta(id="w10_image", kind="openai_compat", source="owned",
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
def _make_project(idea: str = "共三集短剧") -> str:
    client = TestClient(app)
    return client.post("/api/projects", json={"idea": idea}, headers=HEADERS).json()["id"]
def _wait_batch(pid: str, timeout: float = 30.0):
    """等这一批生成跑完。"""
    import time
    client = TestClient(app)
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS).json()
        if r.get("total") and r.get("done", 0) >= r.get("total", 0):
            return r
        time.sleep(0.2)
    raise AssertionError("生成批次没有在超时内完成")
def test_progress_items_carry_media_url(img_server):
    """每个完成的镜头都要带 media_url，界面才能显示真实画面。"""
    REGISTRY.register(_LocalImageProvider(img_server))
    pid = _make_project()
    client = TestClient(app)
    client.post(f"/api/projects/{pid}/generation/start", headers=HEADERS, json={"shot_count": 2})
    prog = _wait_batch(pid)
    assert len(prog["items"]) == 2
    for it in prog["items"]:
        assert it["status"] == "done", it
        assert it.get("media_url"), f"缺少 media_url：{it}"
        assert it["media_url"].startswith("/api/assets/")
        # 地址必须是本机素材端点（永久有效），不能是厂商临时链接
        assert "token=" in it["media_url"]
def test_media_url_serves_the_real_file(img_server):
    REGISTRY.register(_LocalImageProvider(img_server))
    pid = _make_project()
    client = TestClient(app)
    client.post(f"/api/projects/{pid}/generation/start", headers=HEADERS, json={"shot_count": 1})
    prog = _wait_batch(pid)
    url = prog["items"][0]["media_url"]
    r = client.get(url)
    assert r.status_code == 200
    assert r.content == PNG_1x1, "缩略图必须是真实图片字节"
def test_regenerate_single_shot(img_server):
    """只重生成一个镜头：其它镜头不动，旧素材作废。"""
    provider = _LocalImageProvider(img_server)
    REGISTRY.register(provider)
    pid = _make_project()
    client = TestClient(app)
    client.post(f"/api/projects/{pid}/generation/start", headers=HEADERS, json={"shot_count": 2})
    prog = _wait_batch(pid)
    first = prog["items"][0]
    other = prog["items"][1]
    old_asset_id = first["asset_id"]
    calls_before = provider.calls
    r = client.post(f"/api/projects/{pid}/shots/{first['shot_id']}/regenerate",
                    headers=HEADERS, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True, body
    assert body["media_url"], body
    assert provider.calls == calls_before + 1, "只应该再调用一次厂商"
    # 旧素材必须作废：否则导出时新旧两张都会被拼进去
    # 注意：库里的 shot_id 带项目前缀（db_shot_id），避免跨项目串台
    from engine.app.workflow.generation import db_shot_id
    with DB.read() as c:
        rows = c.execute(
            "SELECT id FROM assets WHERE project_id=? AND shot_id=?",
            (pid, db_shot_id(pid, first["shot_id"])),
        ).fetchall()
    ids = [x["id"] for x in rows]
    assert old_asset_id not in ids, f"旧素材没被清掉：{ids}"
    # 另一个镜头的素材不受影响
    with DB.read() as c:
        n = c.execute(
            "SELECT COUNT(*) FROM assets WHERE project_id=? AND shot_id=?",
            (pid, db_shot_id(pid, other["shot_id"])),
        ).fetchone()[0]
    assert n >= 1, "别的镜头素材不该被动"
def test_regenerate_unknown_shot_is_rejected(img_server):
    REGISTRY.register(_LocalImageProvider(img_server))
    pid = _make_project()
    client = TestClient(app)
    client.post(f"/api/projects/{pid}/generation/start", headers=HEADERS, json={"shot_count": 1})
    _wait_batch(pid)
    r = client.post(f"/api/projects/{pid}/shots/s999/regenerate", headers=HEADERS, json={})
    assert r.status_code == 400, r.text
    assert "找不到镜头" in r.text
def test_regenerate_without_batch_is_rejected():
    """没跑过生成就说"重生成第 3 镜"要明确拒绝，不能静默。"""
    pid = _make_project()
    client = TestClient(app)
    r = client.post(f"/api/projects/{pid}/shots/s1/regenerate", headers=HEADERS, json={})
    assert r.status_code == 400, r.text
    assert "生成批次" in r.text
def test_legacy_assets_without_shot_id_still_get_media_url(img_server):
    """老项目没写 assets.shot_id：也要能按顺序显示出画面，不能一片空白。"""
    REGISTRY.register(_LocalImageProvider(img_server))
    pid = _make_project()
    client = TestClient(app)
    client.post(f"/api/projects/{pid}/generation/start", headers=HEADERS, json={"shot_count": 2})
    _wait_batch(pid)
    # 模拟老数据：把关联清掉
    with DB.tx() as c:
        c.execute("UPDATE assets SET shot_id=NULL WHERE project_id=?", (pid,))
    prog = client.get(f"/api/projects/{pid}/generation/progress", headers=HEADERS).json()
    for it in prog["items"]:
        assert it.get("media_url"), f"老素材没有兜底地址：{it}"
        assert client.get(it["media_url"]).status_code == 200
def test_work_preview_supports_range():
    """成片预览必须支持 Range，否则浏览器不能拖进度条。"""
    client = TestClient(app)
    pid = _make_project()
    # 直接造一个成片文件与登记行
    work_id = "wk_preview_test"
    from engine.app.storage.util import utc_now
    p = ASSETS.data_dir / "works" / f"{work_id}.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"0" * 1000)
    DB.insert("assets", {
        "id": work_id, "project_id": pid, "kind": "work",
        "local_path": ASSETS.rel_path(p), "sha256": "x", "size_bytes": 1000,
    })
    # 无 Range → 整段
    r = client.get(f"/api/works/{work_id}/preview?token={LOCAL_TOKEN}")
    assert r.status_code == 200
    assert r.headers.get("accept-ranges") == "bytes"
    # 带 Range → 206 + Content-Range
    r = client.get(f"/api/works/{work_id}/preview?token={LOCAL_TOKEN}",
                   headers={"Range": "bytes=0-99"})
    assert r.status_code == 206, r.status_code
    assert r.headers.get("content-range") == "bytes 0-99/1000"
    assert len(r.content) == 100
def test_work_preview_requires_token():
    client = TestClient(app)
    r = client.get("/api/works/whatever/preview?token=wrong")
    assert r.status_code == 401
