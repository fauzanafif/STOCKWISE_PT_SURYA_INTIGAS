"""SQLite access. stockwise.db is the single source of truth (spec §22).

Read-heavy: the Streamlit pages call `read_df()` / `fetch_all()`. Writes happen
only through the ingest pipeline and the matching-review / calc actions.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

import pandas as pd

from stockwise.config import DB_PATH, SCHEMA_PATH


def connect(readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        uri = f"file:{DB_PATH}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def cursor(commit: bool = False):
    conn = connect()
    try:
        yield conn
        if commit:
            conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create the schema if the file is new. Idempotent (schema uses IF NOT EXISTS)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def db_exists() -> bool:
    return DB_PATH.exists() and DB_PATH.stat().st_size > 0


def read_df(sql: str, params: tuple | dict = ()) -> pd.DataFrame:
    conn = connect(readonly=db_exists())
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def fetch_all(sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
    with cursor() as conn:
        return conn.execute(sql, params).fetchall()


def fetch_one(sql: str, params: tuple | dict = ()):
    with cursor() as conn:
        return conn.execute(sql, params).fetchone()


def scalar(sql: str, params: tuple | dict = ()):
    row = fetch_one(sql, params)
    return None if row is None else row[0]
