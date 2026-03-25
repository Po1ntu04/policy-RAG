"""Postgres connection helpers (lightweight, no ORM)."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from private_gpt.settings.settings import settings

logger = logging.getLogger(__name__)

_pool = None


def _load_psycopg2():
    try:
        import psycopg2
        import psycopg2.pool
        import psycopg2.extras
    except Exception as exc:  # pragma: no cover - import guard
        raise ImportError(
            "psycopg2 is required for Postgres support. "
            "Install with: poetry add psycopg2-binary"
        ) from exc
    return psycopg2


def _get_dsn() -> str:
    cfg = settings().postgres
    if cfg is None:
        raise RuntimeError("Postgres settings not configured.")
    return (
        f"host={cfg.host} port={cfg.port} dbname={cfg.database} "
        f"user={cfg.user} password={cfg.password}"
    )


def get_pool():
    global _pool
    if _pool is None:
        psycopg2 = _load_psycopg2()
        maxconn = int(os.getenv("PGPT_DB_MAXCONN", "5"))
        _pool = psycopg2.pool.SimpleConnectionPool(1, maxconn, dsn=_get_dsn())
        logger.info("Postgres pool initialized (maxconn=%s).", maxconn)
    return _pool


@contextmanager
def get_connection() -> Iterator:
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def run_sql_file(file_path: str) -> None:
    psycopg2 = _load_psycopg2()
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {file_path}")
    sql = path.read_text(encoding="utf-8")
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    with get_connection() as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)
    logger.info("Executed SQL file: %s", file_path)


def auto_migrate() -> None:
    """Apply schema/seed automatically when PGPT_AUTO_MIGRATE=1."""
    if os.getenv("PGPT_AUTO_MIGRATE", "0") != "1":
        return
    base = Path(__file__).resolve().parents[3]
    schema_file = base / "db" / "schema_postgres.sql"
    seed_file = base / "db" / "seed.sql"
    try:
        run_sql_file(str(schema_file))
        run_sql_file(str(seed_file))
        logger.info("Auto-migrate completed.")
    except Exception as exc:
        logger.error("Auto-migrate failed: %s", exc)
        raise
