"""素材落地存储：厂商临时链接 → 本机文件 + assets 表登记。
为什么必须落地（2026-11-21 修复）：
- 厂商返回的是带签名、有有效期的临时链接（SenseNova 给的是 24 小时后过期的
  预签名 OSS 链接）。直接把这个链接存进项目，链接一过期，项目里的画面就全部
  变裂图，用户之前生成的成果等于丢了。
- 界面还有 CSP 限制，外链图片在应用内不一定能显示。
所以：生成到素材后立刻下载到本机 data/assets/<project_id>/，登记 assets 表，
界面一律读本机文件；下载失败时保留原厂链接兜底，不谎报成功。
"""
from __future__ import annotations
import base64
import binascii
import hashlib
import mimetypes
from pathlib import Path
from typing import Any
import httpx
from ..storage.db import Database
from ..storage.util import ulid
# 允许下载的最大体积（字节）。视频通常几 MB，预签名链接失效前必须取回。
MAX_BYTES = 512 * 1024 * 1024
_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
}
class AssetStore:
    """素材仓库：落盘 + 登记 + 路径解析。"""
    def __init__(self, db: Database, data_dir: Path):
        self.db = db
        self.data_dir = Path(data_dir)
        self.root = self.data_dir / "assets"
    # ---------- 路径 ----------
    def resolve(self, local_path: str) -> Path:
        """把库里的相对路径解析成真实文件路径。
        库里存的是相对用户数据目录的路径（数据目录可迁移）；历史上也有直接存
        绝对路径的行，这里两种都兼容。
        """
        p = Path(local_path)
        if p.is_absolute():
            return p
        return self.data_dir / p
    def _rel(self, path: Path) -> str:
        """存库用相对路径（相对数据目录）。"""
        try:
            return path.relative_to(self.data_dir).as_posix()
        except ValueError:
            return path.as_posix()
    def rel_path(self, path: str | Path) -> str:
        """对外版：把任意路径转成库内使用的相对路径。
        存绝对路径的坏处：数据目录一迁移，库里所有素材路径集体失效。
        """
        p = Path(path)
        if p.is_absolute():
            return self._rel(p)
        return p.as_posix()
    # ---------- 写入 ----------
    def save_bytes(
        self,
        project_id: str,
        kind: str,
        data: bytes,
        *,
        ext: str = ".bin",
        character_id: str | None = None,
        shot_id: str | None = None,
        source_url: str | None = None,
    ) -> dict[str, Any] | None:
        """把二进制内容落盘并登记 assets 表，返回素材行。"""
        if not data:
            return None
        asset_id = ulid()
        folder = self.root / project_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{asset_id}{ext}"
        path.write_bytes(data)
        row = {
            "id": asset_id,
            "project_id": project_id,
            "kind": kind,
            "local_path": self._rel(path),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "character_id": character_id,
            "shot_id": shot_id,
        }
        try:
            self.db.insert("assets", row)
        except Exception:  # noqa: BLE001
            # 外键指向的角色/镜头行可能还没落库：素材本身不能丢，退一步不带外键登记
            row["character_id"] = None
            row["shot_id"] = None
            self.db.insert("assets", row)
        row["source_url"] = source_url
        return row
    def save_remote(
        self,
        project_id: str,
        kind: str,
        url: str,
        *,
        character_id: str | None = None,
        shot_id: str | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any] | None:
        """下载厂商链接并落地。失败返回 None（调用方保留原链接兜底）。"""
        if not url:
            return None
        if url.startswith("data:"):
            return self._save_data_url(project_id, kind, url, character_id=character_id, shot_id=shot_id)
        if not url.startswith("http://") and not url.startswith("https://"):
            return None
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as c:
                with c.stream("GET", url) as r:
                    if r.status_code != 200:
                        return None
                    ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
                    total = int(r.headers.get("content-length") or 0)
                    if total and total > MAX_BYTES:
                        return None
                    buf = bytearray()
                    for chunk in r.iter_bytes():
                        buf.extend(chunk)
                        if len(buf) > MAX_BYTES:
                            return None
                    data = bytes(buf)
        except Exception:  # noqa: BLE001 - 下载失败不致命，调用方回退原链接
            return None
        ext = _EXT_BY_MIME.get(ctype) or (Path(url.split("?")[0]).suffix or ".bin")
        if len(ext) > 6 or "/" in ext:
            ext = ".bin"
        return self.save_bytes(
            project_id, kind, data, ext=ext,
            character_id=character_id, shot_id=shot_id, source_url=url,
        )
    def _save_data_url(
        self,
        project_id: str,
        kind: str,
        url: str,
        *,
        character_id: str | None = None,
        shot_id: str | None = None,
    ) -> dict[str, Any] | None:
        """部分厂商直接返回 base64 图片（b64_json），这里落盘成真实文件。"""
        try:
            head, b64 = url.split(",", 1)
        except ValueError:
            return None
        if "base64" not in head:
            return None
        mime = head[5:].split(";")[0] or "image/png"
        try:
            data = base64.b64decode(b64, validate=False)
        except (binascii.Error, ValueError):
            return None
        ext = _EXT_BY_MIME.get(mime.lower(), ".png")
        return self.save_bytes(
            project_id, kind, data, ext=ext,
            character_id=character_id, shot_id=shot_id,
        )
    # ---------- 读取 ----------
    def list_project(self, project_id: str) -> list[dict[str, Any]]:
        rows = self.db.list(
            "SELECT * FROM assets WHERE project_id=? AND kind<>'work' ORDER BY created_at",
            (project_id,),
        )
        for r in rows:
            r["exists"] = self.resolve(r["local_path"]).exists()
        return rows
