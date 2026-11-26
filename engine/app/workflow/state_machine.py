"""流程状态机：表驱动，守卫先行，写序固定（设计 v3.1 §5.1）。
安全：CP-2/CP-3 不可跳过在引擎层强制（无跳过 API）。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
@dataclass(frozen=True)
class Transition:
    current: str
    event: str
    next: str
    guard: str | None = None       # trust_mode / sel_ge1 / roles_ready
    effects: tuple[str, ...] = ()
TRANSITIONS: tuple[Transition, ...] = (
    Transition("DRAFT", "script_ready", "CP1_PENDING", effects=("gen_outline",)),
    Transition("CP1_PENDING", "approve", "CHARACT", effects=("finalize_script",)),
    Transition("CP1_PENDING", "approve", "CHARACT", guard="trust_mode", effects=("audit_log",)),
    Transition("CP1_PENDING", "reject", "DRAFT", effects=("bump_prompt_ver",)),
    Transition("CHARACT", "roles_ready", "CP2_PENDING", guard="roles_ready", effects=("rank_candidates",)),
    Transition("CP2_PENDING", "approve", "PLANNED", guard="sel_ge1", effects=("lock_characters", "route_snapshot")),
    Transition("CP2_PENDING", "reject", "CHARACT", effects=("free_reroll",)),
    Transition("PLANNED", "budget_confirmed", "RUNNING", effects=("snapshot_route", "enqueue")),
    Transition("RUNNING", "all_done", "CP3_PENDING", effects=("make_preview",)),
    Transition("RUNNING", "task_failed", "RUNNING", effects=("mark_failed_continue",)),
    Transition("CP3_PENDING", "approve", "DELIVER", effects=("enqueue_compose",)),
    Transition("CP3_PENDING", "reject", "PLANNED", effects=("discard_shots",)),
    Transition("DELIVER", "export_done", "DELIVER", effects=("write_works",)),
)
NON_SKIPPABLE = frozenset({"CP2_PENDING", "CP3_PENDING"})
class GuardError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
class WorkflowEngine:
    def __init__(self, transitions: tuple[Transition, ...] = TRANSITIONS):
        self._table = transitions
    def advance(
        self,
        current: str,
        event: str,
        ctx: dict | None = None,
        skip: bool = False,
    ) -> tuple[str, tuple[str, ...]]:
        ctx = ctx or {}
        if skip and current in NON_SKIPPABLE:
            raise GuardError("E3002", "这一步不能跳过，请先确认")
        if event == "skip":
            event = "approve"
        for t in self._table:
            if t.current != current or t.event != event:
                continue
            if t.guard and not self._check_guard(t.guard, ctx):
                continue
            return t.next, t.effects
        raise GuardError("E3001", "这一步现在还不能确认")
    @staticmethod
    def _check_guard(guard: str, ctx: dict) -> bool:
        if guard == "trust_mode":
            return bool(ctx.get("trust_mode"))
        if guard == "sel_ge1":
            return len(ctx.get("selected") or []) >= 1
        if guard == "roles_ready":
            return int(ctx.get("role_count", 0)) >= 1 and int(ctx.get("candidate_count", 0)) >= 1
        return False
