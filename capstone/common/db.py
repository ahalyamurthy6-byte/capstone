from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pgvector.psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from common.config import get_settings


_settings = get_settings()
_pool: ConnectionPool | None = None


def _configure(conn: Any) -> None:
    pgvector.psycopg.register_vector(conn)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=_settings.DATABASE_URL,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
            configure=_configure,
            open=True,
        )
    return _pool


@contextmanager
def get_conn():
    with get_pool().connection() as conn:
        yield conn


def fetch_one(sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return dict(row) if row is not None else None


def fetch_all(sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        return [dict(row) for row in rows]


def execute(sql: str, params: tuple[Any, ...] | None = None) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        return cur.rowcount
