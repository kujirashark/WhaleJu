"""对话 Agent：工具白名单 + 意图改写 + 确认门（设计 v3.1 §5.3）。
Never 层：白名单没有 approve_checkpoint / start_generation / 扣费工具。
未确认的写操作一律不执行——Agent 不能"顺手"替用户花钱。
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any
ALLOWED_TOOLS = frozenset({
    "get_script", "get_shots", "get_characters",
    "regen_script", "adjust_pacing", "swap_role_image",
    "answer_question", "route_to_recharge", "route_to_settings",
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
    (("太快", "节奏", "慢一点", "铺垫"), "adjust_pacing", 9.0, "在铺垫处多加一个镜头"),
    (("换脸", "形象", "重做角色", "角色不像"), "swap_role_image", 0.0, "重新生成角色参考图"),
    (("重写", "改剧本", "换一版", "不满意"), "regen_script", 0.0, "按你的意见重写剧本"),
    (("额度", "充值", "没钱", "费用"), "route_to_recharge", 0.0, "去充值额度"),
)
class ConversationAgent:
    def __init__(self, llm_caller=None):
        self.llm_caller = llm_caller
    def classify(self, text: str) -> str:
        for keys, op, _, _ in _RULES:
            if any(k in text for k in keys):
                return op
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
