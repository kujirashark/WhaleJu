"""额度钱包：冻结 → 结算 → 退回，双源记账（设计 v3.1 §5.4）。"""
from __future__ import annotations
from ..storage.db import Database
from ..storage.util import dumps, ulid, utc_now
class InsufficientCredits(Exception):
    pass
class CreditLedger:
    def __init__(self, db: Database):
        self.db = db
    def wallet(self) -> dict:
        with self.db.read() as c:
            row = c.execute("SELECT balance, frozen, synced_at FROM credit_wallet WHERE id=1").fetchone()
        return dict(row) if row else {"balance": 0.0, "frozen": 0.0, "synced_at": None}
    def freeze(self, amount: float, project_id: str, provider_id: str, ability: str) -> str:
        if amount < 0:
            raise ValueError("amount must be >= 0")
        with self.db.tx() as c:
            row = c.execute("SELECT balance, frozen FROM credit_wallet WHERE id=1").fetchone()
            if row["balance"] - row["frozen"] < amount:
                raise InsufficientCredits(f"额度不足：需要 {amount}，可用 {row['balance'] - row['frozen']}")
            c.execute("UPDATE credit_wallet SET frozen=frozen+? WHERE id=1", (amount,))
            event_id = ulid()
            c.execute(
                """INSERT INTO usage_events(id,ts,project_id,provider_id,source,ability,units,credits_spent,raw_cost_estimate,ok)
                   VALUES(?,?,?,?,?,?,?,?,?,0)""",
                (event_id, utc_now(), project_id, provider_id, "proxy", ability, 0, 0, amount),
            )
        return event_id
    def settle(self, event_id: str, actual: float, ok: bool, fail_reason: str | None = None) -> None:
        """冻结金额从 raw_cost_estimate 读取；退回差额；失败全额退回。"""
        with self.db.tx() as c:
            row = c.execute(
                "SELECT raw_cost_estimate AS frozen_amt FROM usage_events WHERE id=?", (event_id,)
            ).fetchone()
            if not row:
                return
            frozen_amt = float(row["frozen_amt"])
            actual = min(max(actual, 0.0), frozen_amt) if ok else 0.0
            c.execute(
                "UPDATE credit_wallet SET frozen=frozen-?, balance=balance-? WHERE id=1",
                (frozen_amt, actual),
            )
            spent = actual * 1.12  # 12% 平台手续费（设计 v3.1 双模式方案）
            c.execute(
                """UPDATE usage_events
                   SET credits_spent=?, ok=?, fail_reason=?, ts=?
                   WHERE id=?""",
                (spent, int(ok), fail_reason, utc_now(), event_id),
            )
    def recharge(self, amount: float, order_id: str) -> None:
        if amount <= 0:
            raise ValueError("amount must be > 0")
        with self.db.tx() as c:
            c.execute("UPDATE credit_wallet SET balance=balance+?, synced_at=? WHERE id=1", (amount, utc_now()))
            c.execute(
                """INSERT INTO usage_events(id,ts,provider_id,source,ability,units,credits_spent,raw_cost_estimate,ok)
                   VALUES(?,?,?,?,?,?,?,?,1)""",
                (ulid(), utc_now(), "gateway", "proxy", "recharge", 0, 0, amount),
            )
