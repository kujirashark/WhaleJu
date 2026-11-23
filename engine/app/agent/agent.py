"""对话 Agent：工具白名单 + 意图改写 + 确认门（设计 v3.1 §5.3）。
Never 层：白名单没有 approve_checkpoint / 扣费工具。
未确认的写操作一律不执行——Agent 不能"顺手"替用户花钱。
流程类意图（写剧本/定妆/拆镜/生成画面/导出）只产出意图，实际调用由前端在
用户确认后执行已有业务接口；Agent 自身不执行写操作，不绕过任何检查点。
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any
ALLOWED_TOOLS = frozenset({
    "get_script", "get_shots", "get_characters",
    "regen_script", "adjust_pacing", "swap_role_image",
    "answer_question", "route_to_recharge", "route_to_settings",
    # 流程驱动意图：仅表达用户想做哪一步，由前端确认后调对应业务接口；
    # 不含 approve_checkpoint / 直接扣费工具，安全边界不变。
    "gen_script", "gen_characters", "gen_shots", "gen_video", "export_video",
    # 界面上不再放流程按钮，统一由对话推进：
    # confirm_step = 确认当前这一步并进入下一步（对应状态机 advance）
    # write_next_episode = 多集项目里接着写下一集（一集一集做，省 token）
    "confirm_step", "write_next_episode",
})
@dataclass
class Intent:
    op: str
    scope: str
    cost_impact: float
    confirm: str
    confirmed: bool = False
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
# 白话 → 结构意图（规则兜底，无需 LLM 即可离线跑通；生产由 LLM 单次调用产出同结构）
_RULES = (
    # op 必须与 ALLOWED_TOOLS 的工具名一致（否则确认后也被白名单拒绝）
    # 修改类放在最前："重写剧本"不能被"写剧本"抢走（那是重写，不是从头写）
    (("太快", "节奏", "慢一点", "铺垫"), "adjust_pacing", 9.0, "在铺垫处多加一个镜头"),
    (("换脸", "形象", "重做角色", "角色不像"), "swap_role_image", 0.0, "重新生成角色参考图"),
    (("重写", "改剧本", "换一版", "不满意", "重新生成这一稿", "重新生成剧本", "再生成一遍", "换一稿"), "regen_script", 0.0, "按你的意见重写剧本"),
    # 流程驱动
    (("开始写剧本", "写剧本", "写第一稿", "生成第一稿", "生成剧本", "开始创作", "写个剧本", "写一部"), "gen_script", 0.0, "用你配置的文本模型生成剧本"),
    (("定妆图", "定妆", "角色形象", "生成角色", "做角色"), "gen_characters", 0.0, "用图片模型生成角色定妆图"),
    (("拆镜头", "拆分镜头", "分镜", "生成镜头"), "gen_shots", 0.0, "用文本模型拆分镜头"),
    (("生成画面", "生成视频", "开始生成", "跑生成", "出画面"), "gen_video", 9.0, "按镜头生成真实画面（约按镜头数计费）"),
    (("导出", "成片", "导出视频"), "export_video", 0.0, "把生成的画面导出成片"),
    (("额度", "充值", "没钱", "费用"), "route_to_recharge", 0.0, "去充值额度"),
    (("设置", "配置模型"), "route_to_settings", 0.0, "打开模型设置"),
    # 多集项目里接着写下一集（一集一集做，省 token）
    (("写第", "续写第", "接着写", "继续写第", "写下一集", "下一集"), "write_next_episode", 0.0, "接着写下一集"),
    # 确认/推进：放在最后兜底，避免抢走"确认剧本并拆镜头"这类复合表达
    (("确认剧本", "确认大纲", "确认形象", "确认角色", "确认这一稿", "确认这一版", "确认这个",
      "可以了", "就这样", "没问题", "好了", "下一步", "往下走", "同意", "认可"), "confirm_step", 0.0, "确认当前这一步并推进到下一步"),
)
# 短句里的"确认 / 好 / 行"：明确是在推进流程，单独处理（长句不算，避免抢问答）
_SHORT_ACK = {"好", "行", "可以", "嗯", "ok", "OK", "好的", "确认", "同意", "没问题", "就这样", "下一步"}
def _is_short_ack(text: str) -> bool:
    """短确认语（<=6 字）且含确认意味 → 推进当前步骤。"""
    t = (text or "").strip()
    if not t or len(t) > 6:
        return False
    return t in _SHORT_ACK or "确认" in t
def _looks_like_creation_request(text: str) -> bool:
    """兜底识别：用户直接给内容规格（数字+集/岁）要求写剧本，但没有显式动词。
    只在所有明确规则都没命中时才调用，避免抢走"第二集太快了""每集换脸"这类修改诉求。
    """
    import re
    # "100集""3集短剧""100岁""从1岁到100岁""改成三集" 等数字+量词规格
    has_spec = bool(re.search(r"\d+\s*(集|岁|部)|[一二三四五六七八九十]+\s*(集|岁|部)", text))
    # 修改/查询类信号：这些不该被识别成"新建剧本"
    modify_signals = ("太快", "太慢", "换脸", "改脸", "不像", "铺垫", "节奏", "重新拆分", "导出", "进度")
    return has_spec and not any(s in text for s in modify_signals)
class ConversationAgent:
    def __init__(self, llm_caller=None):
        self.llm_caller = llm_caller
    def classify(self, text: str) -> str:
        t = (text or "").strip()
        # 短确认语（"确认""好了""下一步"）→ 直接推进当前步骤。
        # 放在最前面：它最短最明确，不会被其它规则误伤。
        if _is_short_ack(t):
            return "confirm_step"
        for keys, op, _, _ in _RULES:
            if any(k in t for k in keys):
                return op
        # 兜底：显式规则没命中，但用户给了创作规格 → 视为写剧本
        if _looks_like_creation_request(t):
            return "gen_script"
        return "answer_question"
    async def rewrite(self, text: str, project_id: str | None = None) -> Intent:
        """把用户口语改写为带成本影响的结构意图；不执行任何写操作。"""
        op = self.classify(text)
        for keys, o, cost, action in _RULES:
            if o == op:
                return Intent(
                    op=o,
                    scope=project_id or "global",
                    cost_impact=cost,
                    confirm=f"你是想{action}吗？" + (f"大约多花 {cost:.0f} 额度，继续吗？" if cost else ""),
                )
        return Intent(
            op="answer_question", scope=project_id or "global",
            cost_impact=0.0, confirm="",
        )
    def execute(self, intent: Intent, **kwargs) -> dict:
        """只有 confirmed=True 且 op 在白名单内才执行。"""
        if not intent.confirmed:
            return {"ok": False, "error": "E3001", "message": "这一步需要你确认后才能继续"}
        if intent.op not in ALLOWED_TOOLS:
            return {"ok": False, "error": "E3002", "message": "这个操作不被允许"}
        return {"ok": True, "op": intent.op, "effects": [f"{intent.op}_done"]}
