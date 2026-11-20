"""SQLite 存储层：连接管理 + schema 初始化 + 通用 CRUD。"""
from __future__ import annotations
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
SCHEMA = Path(__file__).with_name("schema.sql")
_local = threading.local()
class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn
    def init_schema(self) -> None:
        conn = self.connect()
        try:
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
            conn.commit()
        finally:
            conn.close()
    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()
    def insert(self, table: str, values: dict[str, Any]) -> str:
        """参数化插入（防 SQL 注入）：table 名由代码白名单提供，不接受外部输入。"""
        cols = ",".join(values)
        marks = ",".join("?" for _ in values)
        with self.tx() as conn:
            conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))
        return values.get("id", "")
    def get(self, table: str, id_: str) -> dict | None:
        with self.read() as conn:
            row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (id_,)).fetchone()
        return dict(row) if row else None
    def list(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.read() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
    def execute(self, sql: str, params: tuple = ()) -> int:
        with self.tx() as conn:
            cur = conn.execute(sql, params)
            return cur.rowcount
