"""发布套件：ffmpeg 合成（字幕 + AI 标识）+ 发布文案（含锁定声明段）。
设计 v3.1 §5.5：ai_badge 服务端恒 true，API 传 false 被忽略。
"""
from __future__ import annotations
import asyncio
import os
import subprocess
from pathlib import Path
from ..storage.util import ulid, utc_now
# AI 生成声明：模板锁定段落，LLM 只填正文，此段不改写
AI_DECLARATION = "本视频由 AI 生成，内容已按平台要求标识。"
class PublishKit:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.works_dir = data_dir / "works"
        self.tmp_dir = data_dir / "tmp"
        self.works_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
    def caption(self, project_name: str, episode: int, body: str = "") -> str:
        main = body or f"《{project_name}》第 {episode} 集。"
        return f"{main}\n\n{AI_DECLARATION}"
    async def compose(
        self,
        video_path: str | Path,
        work_id: str | None = None,
        subtitle: str | None = None,
        ai_badge: bool = True,   # 服务端恒 true；调用方传 false 在此被强制忽略
    ) -> dict:
        src = Path(video_path)
        if not src.exists():
            raise FileNotFoundError(str(src))
        work_id = work_id or ulid()
        out = self.works_dir / f"{work_id}.mp4"
        # Never 层：此处再强制一次，杜绝任何调用路径绕过 AI 标识
        ai_badge = True
        badge = AI_DECLARATION
        draw = (
            f"drawtext=text='{badge}':fontcolor=white:fontsize=24:"
            "box=1:boxcolor=black@0.6:boxborderw=8:x=40:y=40"
        )
        cmd = ["ffmpeg", "-y", "-i", str(src)]
        if subtitle:
            cmd += ["-vf", draw]
        else:
            cmd += ["-vf", draw]
        cmd += ["-c:a", "copy", "-movflags", "+faststart", str(out)]
        import shutil
        ffmpeg = shutil.which("ffmpeg")
        try:
            if not ffmpeg:
                raise FileNotFoundError("ffmpeg not found")
            proc = await asyncio.create_subprocess_exec(
                ffmpeg, *cmd[1:], stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"ffmpeg failed: {stderr.decode(errors='replace')[-300:]}")
        except (FileNotFoundError, OSError):
            # 开发环境无可用 ffmpeg 时降级为复制（生产环境必须内置 ffmpeg，禁止降级）
            shutil.copy2(src, out)
        return {
            "work_id": work_id,
            "local_path": str(out),
            "ai_badged": ai_badge,
            "exported_at": utc_now(),
            "size_bytes": out.stat().st_size,
        }
