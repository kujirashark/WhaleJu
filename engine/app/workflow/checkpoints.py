"""检查点管理：挂起现场持久化 + 崩溃恢复（设计 v3.1 §5.1/§3.3.4）。
关键：先写库再弹窗；CP 挂起态重启后重新弹窗，绝不自动 approve。
"""
from __future__ import annotations
from ..storage.db import Database
from ..storage.util import dumps, loads, ulid, utc_now
CP_BY_STATUS = {
    "CP1_PENDING": "cp1",
    "CP2_PENDING": "cp2",
    "CP3_PENDING": "cp3",
}
class CheckpointManager:
    def __init__(self, db: Database):
        self.db = db
    def suspend(self, project_id: str, status: str, snapshot: dict) -> str:
        cp_type = CP_BY_STATUS.get(status)
        if not cp_type:
            raise ValueError(f"{status} 不是检查点挂起态")
        cp_id = ulid()
        with self.db.tx() as c:
            # 同项目同类型旧 pending 记录作废（保留审计）
            c.execute(
                "UPDATE checkpoints SET status='rejected' WHERE project_id=? AND type=? AND status='pending'",
                (project_id, cp_type),
            )
            c.execute(
                """INSERT INTO checkpoints(id,project_id,type,status,resume_payload)
                   VALUES(?,?,?,'pending',?)""",
                (cp_id, project_id, cp_type, dumps(snapshot)),
            )
        return cp_id
    def decide(self, cp_id: str, approve: bool, extra: dict | None = None) -> dict:
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM checkpoints WHERE id=?", (cp_id,)).fetchone()
            if not row or row["status"] != "pending":
                raise ValueError("检查点不存在或已决策")
            snapshot = loads(row["resume_payload"], {})
            if extra:
                snapshot.update(extra)
            c.execute(
                "UPDATE checkpoints SET status=?, resume_payload=?, decided_at=? WHERE id=?",
                ("approved" if approve else "rejected", dumps(snapshot), utc_now(), cp_id),
            )
        return snapshot
    def pending_for(self, project_id: str) -> list[dict]:
        return self.db.list(
            "SELECT * FROM checkpoints WHERE project_id=? AND status='pending' ORDER BY created_at",
            (project_id,),
        )
    def recover(self) -> list[dict]:
        """引擎启动时扫描：返回所有需重新弹窗的挂起检查点（不自动 approve）。"""
        return self.db.list(
            """SELECT c.*, p.status AS project_status FROM checkpoints c
               JOIN projects p ON p.id=c.project_id
               WHERE c.status='pending' AND p.deleted_at IS NULL
               ORDER BY c.created_at"""
        )
