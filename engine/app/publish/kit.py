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
# ffmpeg 可执行文件的最小合理体积：真实的 ffmpeg 至少几 MB。
# WinGet 的 Links 目录里会留下 0 字节的失效 shim，用它做阈值正好把假货挡掉。
_FFMPEG_MIN_SIZE = 1 << 20   # 1 MiB
def _is_real_ffmpeg(path: Path | str | None) -> bool:
    """校验候选路径是不是一个真的能跑的 ffmpeg（排除 0 字节 shim）。"""
    if not path:
        return False
    p = Path(path)
    try:
        if not p.is_file():
            return False
        if p.stat().st_size < _FFMPEG_MIN_SIZE:
            return False
    except OSError:
        return False
    return True
def _font_file() -> str | None:
    """找一个能写中文的字体文件。
    ffmpeg 的 drawtext 找不到默认字体时会直接失败（"Cannot find a valid font"），
    Windows 上必须显式给 fontfile。这里按优先级找微软雅黑 / 黑体。
    """
    win = Path(os.environ.get("WINDIR", "C:/Windows"))
    candidates = [
        win / "Fonts" / "msyh.ttc",
        win / "Fonts" / "msyhl.ttc",
        win / "Fonts" / "simhei.ttf",
        win / "Fonts" / "simsun.ttc",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    for c in candidates:
        try:
            if c.is_file() and c.stat().st_size > 0:
                # ffmpeg 的 filter 参数里 Windows 路径的反斜杠要转义
                return str(c).replace("\\", "/").replace(":", r"\:")
        except OSError:
            continue
    return None
def _candidate_dirs() -> list[Path]:
    """按优先级列出可能装了 ffmpeg 的目录。"""
    dirs: list[Path] = []
    # 1) 用户显式指定
    env = os.environ.get("WHALESHARK_FFMPEG") or os.environ.get("FFMPEG_BINARY")
    if env:
        dirs.append(Path(env).parent)
    # 2) Windows 包管理器留下的真实安装目录（WinGet / scoop / chocolatey）
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")),
    ]
    if local:
        winget_pkgs = local / "Microsoft" / "WinGet" / "Packages"
        if winget_pkgs.is_dir():
            try:
                for pkg in winget_pkgs.iterdir():
                    if "ffmpeg" in pkg.name.lower():
                        dirs.append(pkg)
            except OSError:
                pass
        scoop = local / "scoop" / "apps" / "ffmpeg"
        if scoop.is_dir():
            dirs.append(scoop)
    for pf in program_files:
        for name in ("ffmpeg", "FFmpeg"):
            d = pf / name
            if d.is_dir():
                dirs.append(d)
    if local:
        for name in ("ffmpeg", "FFmpeg"):
            d = local / name
            if d.is_dir():
                dirs.append(d)
    for d in ("C:/ffmpeg", "C:/ffmpeg/bin", "C:/ProgramData/chocolatey/bin"):
        p = Path(d)
        if p.is_dir():
            dirs.append(p)
    return dirs
def _ffmpeg_path() -> str | None:
    """找一个真正能跑的 ffmpeg。
    历史坑：Windows 上 WinGet 之类的包管理会在 PATH 里留下 0 字节的失效 shim，
    shutil.which() 会把它当命中，但执行时报"不是有效的 Win32 应用程序"。
    只查 PATH 会漏掉真实安装位置（WinGet 的包目录里就有完整的 ffmpeg），
    导致明明装了却报"本机没有 ffmpeg"。
    现在的顺序：
      1) 环境变量 WHALESHARK_FFMPEG / FFMPEG_BINARY 显式指定
      2) PATH 上的 ffmpeg（校验体积，0 字节 shim 直接跳过）
      3) 包管理器目录与常见安装位置递归查找
    """
    # 1) 显式指定优先
    for env_key in ("WHALESHARK_FFMPEG", "FFMPEG_BINARY"):
        env = os.environ.get(env_key)
        if env and _is_real_ffmpeg(env):
            return env
    # 2) PATH
    exe = shutil.which("ffmpeg")
    if _is_real_ffmpeg(exe):
        return exe
    # 3) 包管理器与常见安装位置
    for d in _candidate_dirs():
        try:
            if not d.is_dir():
                continue
            # 先看常见子目录（bin/），再看目录本身
            for sub in (d / "bin", d):
                if not sub.is_dir():
                    continue
                for cand in sub.glob("ffmpeg.exe"):
                    if _is_real_ffmpeg(cand):
                        return str(cand)
                for cand in sub.glob("ffmpeg"):
                    if _is_real_ffmpeg(cand):
                        return str(cand)
            # 再递归一层（如 ffmpeg-9.0.2-full_build\bin\ffmpeg.exe）
            for cand in d.glob("*/bin/ffmpeg.exe"):
                if _is_real_ffmpeg(cand):
                    return str(cand)
        except OSError:
            continue
    return None
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
        """给视频素材打上 AI 标识并输出成片。
        不允许"降级为复制"：复制出来的文件没有 AI 标识，
        等于给用户一条会被平台判违规的路径，宁可明确报错。
        """
        src = Path(video_path)
        if not src.exists():
            raise FileNotFoundError(str(src))
        work_id = work_id or ulid()
        out = self.works_dir / f"{work_id}.mp4"
        # Never 层：此处再强制一次，杜绝任何调用路径绕过 AI 标识
        ai_badge = True
        badge = AI_DECLARATION
        ffmpeg = _ffmpeg_path()
        if not ffmpeg:
            raise RuntimeError(
                "本机没有可用的 ffmpeg，无法给成片写入 AI 生成标识。"
                "为避免导出未标识的视频（会被平台判违规），已停止导出。"
            )
        font = _font_file()
        draw = (
            f"drawtext=text='{badge}':fontcolor=white:fontsize=24:"
            "box=1:boxcolor=black@0.6:boxborderw=8:x=40:y=40"
        )
        if font:
            draw = draw.replace(":fontcolor", f":fontfile='{font}':fontcolor")
        cmd = [
            ffmpeg, "-y", "-i", str(src),
            "-vf", draw,
            "-c:a", "copy", "-movflags", "+faststart", str(out),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
        except OSError as exc:
            raise RuntimeError(f"本机的 ffmpeg 无法运行：{exc}") from exc
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(f"合成失败：{stderr.decode(errors='replace')[-300:]}")
        return {
            "work_id": work_id,
            "local_path": str(out),
            "ai_badged": ai_badge,
            "format": "mp4",
            "needs_ffmpeg": False,
            "exported_at": utc_now(),
            "size_bytes": out.stat().st_size,
        }
    def export_frames(
        self,
        images: list[Path],
        project_id: str = "",
        project_name: str = "",
        work_id: str | None = None,
    ) -> dict:
        """没有 ffmpeg 时的兜底导出：把画面素材包放到作品库目录。
        不能合成 mp4 就不合成，但成果必须交到用户手上 ——
        目录里放好所有画面 + 一份说明，装上 ffmpeg 后可以自行合成。
        复用同一项目的目录：重复点"重新导出"不会再堆出几份几十 MB 的副本。
        """
        work_id = work_id or ulid()
        folder = self.works_dir / f"{work_id}_frames"
        # 复用：清掉上一次的画面，只留当前这一批
        if folder.exists():
            for old in folder.glob("*"):
                try:
                    if old.is_file():
                        old.unlink()
                    else:
                        shutil.rmtree(old, ignore_errors=True)
                except OSError:
                    pass
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
        # 附带一份 ffmpeg 合成命令行，用户装好 ffmpeg 后可直接粘贴执行
        shots = sorted(
            [p for p in folder.iterdir()
             if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")],
            key=lambda p: p.name,
        )
        listing = folder / "列表.txt"
        listing.write_text(
            "\n".join(f"file '{p.name}'\nduration 2" for p in shots),
            encoding="utf-8",
        )
        (folder / "说明.txt").write_text(
            f"项目：{project_name}\n"
            f"这是本机真实生成的画面素材（共 {copied} 张），按顺序排列。\n"
            "本机没有可用的 ffmpeg，所以没能自动合成 mp4。\n"
            "装好 ffmpeg 后可在本目录执行（每张 2 秒，竖屏 720x1280）：\n"
            '  ffmpeg -f concat -safe 0 -i 列表.txt -vf "scale=720:1280:force_original_aspect_ratio=decrease,'
            'pad=720:1280:(ow-iw)/2:(oh-ih)/2" -r 30 -c:v libx264 -pix_fmt yuv420p 成片.mp4\n'
            "本内容由 AI 生成，发布前请按平台要求完成备案与 AI 标识。\n",
            encoding="utf-8",
        )
        return {
            "work_id": work_id,
            "local_path": str(folder),
            "ai_badged": True,
            "frames": copied,
            "needs_ffmpeg": True,
            "format": "frames",
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
        # 竖屏 1080×1920 / 横屏 1920×1080：主流平台都收这个规格，
        # 720p 上传后平台还会再压一次，画质白丢。
        width, height = (1080, 1920) if ratio == "9:16" else (1920, 1080)
        font = _font_file()
        badge_vf = (
            f"drawtext=text='{AI_DECLARATION}':fontfile='{font}':"
            "fontcolor=white:fontsize=20:box=1:boxcolor=black@0.6:boxborderw=8:x=24:y=24"
            if font else
            f"drawtext=text='{AI_DECLARATION}':fontcolor=white:fontsize=20:"
            "box=1:boxcolor=black@0.6:boxborderw=8:x=24:y=24"
        )
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,{badge_vf}"
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
        return {
            "work_id": work_id,
            "local_path": str(out),
            "ai_badged": True,
            "frames": len(files),
            "format": "mp4",
            "ratio": ratio,
            "needs_ffmpeg": False,
            "exported_at": utc_now(),
            "size_bytes": out.stat().st_size,
        }
