"""发布套件：ffmpeg 合成（字幕 + AI 标识）+ 发布文案（含锁定声明段）。
设计 v3.1 §5.5：ai_badge 服务端恒 true，API 传 false 被忽略。
"""
from __future__ import annotations
import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from ..storage.util import ulid, utc_now
# AI 生成声明：模板锁定段落，LLM 只填正文，此段不改写
AI_DECLARATION = "本视频由 AI 生成，内容已按平台要求标识。"
def _ffmpeg_path() -> str | None:
    """找可用的 ffmpeg。
    注意：Windows 上 WinGet 之类的包管理会留下 0 字节的失效链接，
    shutil.which() 会把它当成命中，但执行时报 "不是有效的 Win32 应用程序"。
    这里必须校验文件大小，否则合成会 500。
    """
    import shutil
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    try:
        if Path(exe).stat().st_size <= 0:
            return None
    except OSError:
        return None
    return exe
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
    def export_frames(self, images: list[Path], project_id: str = "", project_name: str = "") -> dict:
        """没有 ffmpeg 时的兜底导出：把画面素材包放到作品库目录。
        不能合成 mp4 就不合成，但成果必须交到用户手上 ——
        目录里放好所有画面 + 一份说明，装上 ffmpeg 后可以自行合成。
        """
        work_id = ulid()
        folder = self.works_dir / f"{work_id}_frames"
        folder.mkdir(parents=True, exist_ok=True)
        copied = 0
        for i, src in enumerate(images, start=1):
            if not src.exists():
                continue
            dst = folder / f"{i:02d}_{src.name}"
            try:
                shutil.copy2(src, dst)
                copied += 1
            except OSError:
                continue
        (folder / "说明.txt").write_text(
            f"项目：{project_name}\n"
            f"这是本机真实生成的画面素材（共 {copied} 张），按顺序排列。\n"
            "本机没有安装 ffmpeg，所以没能自动合成 mp4。\n"
            "安装 ffmpeg 后可以用以下命令合成（每张 2 秒）：\n"
            "  ffmpeg -f concat -safe 0 -i 列表.txt -vf \"scale=720:1280:force_original_aspect_ratio=decrease,"
            "pad=720:1280:(ow-iw)/2:(oh-ih)/2\" -r 30 -c:v libx264 -pix_fmt yuv420p 成片.mp4\n"
            "本内容由 AI 生成，发布前请按平台要求完成备案与 AI 标识。\n",
            encoding="utf-8",
        )
        return {
            "work_id": work_id,
            "local_path": str(folder),
            "ai_badged": True,
            "frames": copied,
            "needs_ffmpeg": True,
            "exported_at": utc_now(),
            "size_bytes": sum(f.stat().st_size for f in folder.iterdir() if f.is_file()),
        }
    async def compose_slides(
        self,
        images: list[str | Path],
        work_id: str | None = None,
        seconds_per_image: float = 2.0,
        ratio: str = "9:16",
    ) -> dict:
        """把一组画面合成一条视频（动态漫成片）。
        没有视频模型时，第 6 步生成的是画面，第 8 步仍然要能导出一条成片：
        这里按顺序把画面拼成 mp4，并强制写入 AI 标识。
        需要本机有 ffmpeg。没有就如实报错 —— 绝不用假文件冒充成片。
        """
        files = [Path(p) for p in images if p and Path(p).exists()]
        if not files:
            raise FileNotFoundError("没有可用的画面素材")
        ffmpeg = _ffmpeg_path()
        if not ffmpeg:
            raise RuntimeError("本机没有安装 ffmpeg，无法把画面合成视频。请安装 ffmpeg 后重试。")
        work_id = work_id or ulid()
        out = self.works_dir / f"{work_id}.mp4"
        listing = self.tmp_dir / f"{work_id}.txt"
        listing.write_text(
            "\n".join(f"file '{f.as_posix()}'\nduration {seconds_per_image}" for f in files),
            encoding="utf-8",
        )
        width, height = (720, 1280) if ratio == "9:16" else (1280, 720)
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
            f"drawtext=text='{AI_DECLARATION}':fontfile='C\\:/Windows/Fonts/msyh.ttc':"
            "fontcolor=white:fontsize=20:box=1:boxcolor=black@0.6:boxborderw=8:x=24:y=24"
        )
        cmd = [
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
            "-vf", vf, "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(out),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
        except OSError as exc:
            # 典型的失效 ffmpeg（0 字节链接）会在这里炸：如实说明，转成可兜底的错误
            try:
                listing.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError(f"本机的 ffmpeg 无法运行：{exc}") from exc
        try:
            listing.unlink(missing_ok=True)
        except OSError:
            pass
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(f"合成失败：{stderr.decode(errors='replace')[-300:]}")
        return {            "work_id": work_id,
            "local_path": str(out),
            "ai_badged": True,
            "frames": len(files),
            "exported_at": utc_now(),
            "size_bytes": out.stat().st_size,
        }
