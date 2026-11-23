"""真实内容生成：用已配置的 text Provider 生成剧本/大纲/镜头。
去演示化要点：
- 没有配置/验证 text 能力 → 明确抛 NoProviderError，不返回任何预置示例文本。
- 调用真实 LLM，把结果结构化后存 projects 表，前端只读引擎事实。
- LLM 返回不可解析时如实报错，不用硬编码剧本冒充生成结果。
"""
from __future__ import annotations
import json
import re
from ..adapters.base import ImageGenRequest, TextGenRequest
from ..adapters.registry import ProviderRegistry
from ..storage.db import Database
from ..storage.util import utc_now
class NoProviderError(Exception):
    def __init__(self, message: str, code: str = "E4001"):
        super().__init__(message)
        self.code = code
class ContentGenerator:
    def __init__(self, db: Database, registry: ProviderRegistry, assets=None):
        self.db = db
        self.registry = registry
        # 素材落地仓库：厂商给的临时链接会过期，必须取回本机
        self.assets = assets
    def _provider(self):
        route = self.registry.route("text", "key")
        if not route:
            raise NoProviderError("还没有配置可用的文本模型，请先到「设置 → 写剧本」配置并测试连接")
        provider = self.registry.get(route.provider_id)
        if not provider:
            raise NoProviderError("文本模型当前不可用，请重新测试连接")
        return provider
    async def _ask(self, prompt: str, system: str) -> str:
        provider = self._provider()
        import asyncio
        tid = await provider.submit(TextGenRequest(prompt=prompt, system=system, max_tokens=2048))
        result = await provider.poll(tid)
        if not result.ok:
            raise NoProviderError(f"文本模型生成失败：{result.fail_reason or '未知错误'}")
        # ConfiguredProvider 把文本正文放在 provider_task_id 字段（避免落盘 asset）
        content = result.provider_task_id or result.asset_ref or ""
        if not content:
            raise NoProviderError("文本模型没有返回内容")
        return content
    @staticmethod
    def _script_prompt(idea: str) -> tuple[str, str]:
        system = (
            "你是短剧编剧。只输出 JSON，不要输出其他文字。格式："
            '{"title":"剧名","episodes":[{"idx":1,"title":"集标题","tags":["标签"],"script":"本集正文"}]}'
            "。写 3 集，每集一个明确的人生阶段，正文 150-250 字，语言口语化。"
        )
        return system, f"根据用户想法写一部 3 集竖屏短剧。用户想法：{idea}"
    def _save_script(self, project_id: str, idea: str, version: int, raw: str) -> dict:
        data, partial = self._parse_json_lenient(raw)
        episodes = data.get("episodes") or []
        payload = {
            "title": str(data.get("title") or idea[:12]),
            "episodes": episodes,
            "version": version,
            "idea": idea,
            "partial": partial,
            "generated_at": utc_now(),
        }
        with self.db.tx() as c:
            c.execute(
                "UPDATE projects SET script_json=?, script_ver=? WHERE id=?",
                (json.dumps(payload, ensure_ascii=False), version, project_id),
            )
        return payload
    async def generate_script(self, project_id: str, idea: str, version: int = 1) -> dict:
        system, prompt = self._script_prompt(idea)
        raw = await self._ask(prompt, system)
        return self._save_script(project_id, idea, version, raw)
    async def stream_script(self, project_id: str, idea: str, version: int = 1):
        """流式生成剧本：逐块 yield 文本增量，完整结果落库后 yield 终帧。
        yield 格式：
        - ("token", 文本片段)
        - ("call", 调用记录)  每一次真实 HTTP 尝试，界面据此显示调用日志
        - ("done", payload)
        失败抛出 NoProviderError，由 API 层转成明确的 SSE error 事件。
        """
        provider = self._provider()
        if not hasattr(provider, "stream_chat"):
            raise NoProviderError("当前模型不支持流式输出，请改用支持 OpenAI 兼容流的模型")
        system, prompt = self._script_prompt(idea)
        chunks: list[str] = []
        try:
            async for item in provider.stream_chat(prompt, system, max_tokens=2048):
                # 兼容两种 Provider：产出 ("delta", text)/("call", log) 的新版，
                # 以及只 yield 纯文本的旧实现。
                if isinstance(item, tuple) and item and item[0] == "call":
                    yield ("call", item[1])
                    continue
                if isinstance(item, tuple) and item and item[0] == "wait":
                    # 限流退避等待：推给界面，避免黑盒
                    yield ("wait", item[1])
                    continue
                delta = item[1] if (isinstance(item, tuple) and item and item[0] == "delta") else item
                if not isinstance(delta, str):
                    continue
                chunks.append(delta)
                yield ("token", delta)
        except Exception as exc:  # noqa: BLE001
            raise NoProviderError(f"文本模型生成失败：{str(exc)[:160]}") from exc
        raw = "".join(chunks)
        if not raw.strip():
            raise NoProviderError("文本模型没有返回内容")
        yield ("done", self._save_script(project_id, idea, version, raw))
    async def generate_shots(self, project_id: str, shot_count: int = 12) -> dict:
        system = (
            "你是分镜师。只输出 JSON，不要输出其他文字。格式："
            '{"shots":[{"idx":1,"scene":"场景描述","importance":"key|transition"}]}'
            f"。输出 {shot_count} 个镜头，其中一半 key、一半 transition，按剧情顺序。"
        )
        with self.db.read() as c:
            row = c.execute("SELECT script_json, idea_text FROM projects WHERE id=?", (project_id,)).fetchone()
        idea = (row["idea_text"] if row else "") or "短剧"
        prompt = f"根据这部剧拆分镜头。剧情：{idea}"
        raw = await self._ask(prompt, system)
        data, partial = self._parse_json_lenient(raw, kind="shots")
        shots = data.get("shots") or []
        payload = {"shots": shots, "partial": partial, "generated_at": utc_now()}
        with self.db.tx() as c:
            c.execute("UPDATE projects SET shots_json=? WHERE id=?",
                      (json.dumps(payload, ensure_ascii=False), project_id))
        return payload
    async def generate_characters(self, project_id: str, count: int = 5) -> list[dict]:
        """用已配置的 image 模型生成定妆参考图；未配置则明确拒绝。
        返回 [{id, name, desc_text, ref_url}]，并落 characters 表。
        生成的图片会立刻下载到本机（assets 目录）并登记 assets 表：
        厂商给的是带签名、会过期的链接，直接存链接的话项目过一天全是裂图。
        下载失败时保留原厂链接兜底，不谎报成功。
        """
        route = self.registry.route("image", "key")
        if not route:
            raise NoProviderError("还没有配置可用的图片模型，请先到「设置 → 生成图片」配置并测试连接")
        provider = self.registry.get(route.provider_id)
        if not provider:
            raise NoProviderError("图片模型当前不可用，请重新测试连接")
        with self.db.read() as c:
            row = c.execute("SELECT idea_text, script_json FROM projects WHERE id=?", (project_id,)).fetchone()
        idea = (row["idea_text"] if row else "") or "短剧"
        result: list[dict] = []
        for i in range(count):
            desc = f"{idea} 中的主要人物，第 {i + 1} 个年龄段/角色，定妆参考图"
            try:
                import asyncio
                tid = await provider.submit(ImageGenRequest(prompt=desc, size="1024x1536"))
                gen = await provider.poll(tid)
                if not gen.ok:
                    raise NoProviderError(f"图片模型生成失败：{gen.fail_reason or '未知错误'}")
                url = ""
                # ConfiguredProvider 把图片 URL 暂存在实例；通过 asset_ref 或重新取
                url = gen.asset_ref or ""
                if not url and hasattr(provider, "_assets"):
                    url = provider._assets.get(tid, "")
                if not url:
                    raise NoProviderError("图片模型没有返回图片地址")
                cid = f"chr_{project_id}_{i + 1}"
                # 先落角色行，再落素材（素材有指向角色的外键，顺序反了会插不进去）
                with self.db.tx() as c:
                    c.execute(
                        """INSERT OR REPLACE INTO characters(id,project_id,name,desc_text,ref_images,locked)
                           VALUES(?,?,?,?,?,0)""",
                        (cid, project_id, f"角色 {i + 1}", desc, json.dumps([], ensure_ascii=False)),
                    )
                # 落地到本机：链接会过期，落地后项目永久可看
                local_path = ""
                asset_id = ""
                if self.assets is not None:
                    asset = self.assets.save_remote(
                        project_id, "character", url, character_id=cid,
                    )
                    if asset:
                        local_path = asset["local_path"]
                        asset_id = asset["id"]
                with self.db.tx() as c:
                    c.execute(
                        """UPDATE characters SET ref_images=? WHERE id=?""",
                        (json.dumps([{
                            "asset_id": asset_id,
                            "url": local_path or url,
                            "remote_url": url,
                            "rank": 1,
                        }], ensure_ascii=False), cid),
                    )
                result.append({
                    "id": cid, "name": f"角色 {i + 1}", "desc_text": desc,
                    "ref_url": local_path or url,
                    "asset_id": asset_id,
                    "remote_url": url,
                    "local_saved": bool(asset_id),
                })
            except NoProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise NoProviderError(f"生成第 {i + 1} 个角色失败：{str(exc)[:80]}")
        return result
    @staticmethod
    def _parse_json(raw: str) -> dict:
        """从模型输出中稳健提取 JSON（容忍 ```json 包裹与前后说明文字）。"""
        text = raw.strip()
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
        if m:
            text = m.group(1)
        else:
            first, last = text.find("{"), text.rfind("}")
            if first >= 0 and last > first:
                text = text[first:last + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise NoProviderError(f"文本模型返回的内容无法解析为剧本：{exc}")
    # ── 残缺输出的降级提取 ──────────────────────────────────────
    # 模型偶尔会被截断（厂商关流、max_tokens 触顶、限流中断），
    # 输出停在半截 JSON 上。此时整份丢弃是可惜的 ——
    # 已经写完的那几集是好的，应该救回来交给用户。
    @staticmethod
    def _unescape(s: str) -> str:
        """把 JSON 字符串片段反转义（片段可能没闭合，但要能安全处理）。"""
        try:
            return json.loads('"' + s + '"')
        except (json.JSONDecodeError, ValueError):
            return (s.replace('\\"', '"').replace("\\n", "\n")
                     .replace("\\t", "\t").replace("\\\\", "\\"))
    def _extract_episodes(self, raw: str) -> list[dict]:
        """从残缺 JSON 里逐个抠出 episode 的 idx/title/tags/script。
        script 的正则允许未闭合（模型正写到一半），
        这样至少能保住"已完整写完的那几集 + 正在写的那一集的部分正文"。
        """
        episodes: list[dict] = []
        marks = list(re.finditer(r'"idx"\s*:\s*(\d+)', raw))
        for i, mk in enumerate(marks):
            seg = raw[mk.start(): marks[i + 1].start() if i + 1 < len(marks) else len(raw)]
            tm = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', seg)
            if not tm:
                continue
            sm = re.search(r'"script"\s*:\s*"((?:[^"\\]|\\.)*)', seg)
            gm = re.search(r'"tags"\s*:\s*\[([^\]]*)\]', seg)
            tags = []
            if gm:
                tags = [self._unescape(t) for t in re.findall(r'"((?:[^"\\]|\\.)*)"', gm.group(1))]
            episodes.append({
                "idx": int(mk.group(1)),
                "title": self._unescape(tm.group(1)),
                "tags": tags,
                "script": self._unescape(sm.group(1)) if sm else "",
            })
        return episodes
    def _extract_shots(self, raw: str) -> list[dict]:
        """从残缺 JSON 里抠出已经写完的镜头。"""
        shots: list[dict] = []
        marks = list(re.finditer(r'"idx"\s*:\s*(\d+)', raw))
        for i, mk in enumerate(marks):
            seg = raw[mk.start(): marks[i + 1].start() if i + 1 < len(marks) else len(raw)]
            sm = re.search(r'"scene"\s*:\s*"((?:[^"\\]|\\.)*)', seg)
            if not sm:
                continue
            im = re.search(r'"importance"\s*:\s*"((?:[^"\\]|\\.)*)"', seg)
            shots.append({
                "idx": int(mk.group(1)),
                "scene": self._unescape(sm.group(1)),
                "importance": self._unescape(im.group(1)) if im else "transition",
            })
        return shots
    def _parse_json_lenient(self, raw: str, kind: str = "script") -> tuple[dict, bool]:
        """解析模型输出。返回 (数据, 是否残缺)。
        残缺时不丢弃：至少保住已经写完的部分，让用户拿到部分成果，
        而不是一句"生成失败"让整轮白跑。
        """
        try:
            return self._parse_json(raw), False
        except NoProviderError as exc:
            if kind == "shots":
                usable = [s for s in self._extract_shots(raw) if (s.get("scene") or "").strip()]
                if usable:
                    return {"shots": usable}, True
            else:
                episodes = self._extract_episodes(raw)
                usable = [e for e in episodes if (e.get("script") or "").strip()]
                if usable:
                    title_m = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
                    title = self._unescape(title_m.group(1)) if title_m else ""
                    return {"title": title, "episodes": usable}, True
            # 连一个完整对象都救不回来：把原始输出片段带上，便于定位
            snippet = raw.strip()[:160].replace("\n", " ")
            raise NoProviderError(
                f"文本模型这次没写完（输出在第 {len(raw.strip())} 个字符处中断），没能解析成剧本。"
                f"已收到的内容开头：{snippet}",
                code="E4004",
            ) from exc
