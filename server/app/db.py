"""SQLite 存储层：候选、生成任务、已发布搭子三张表 + 统计计数。

隐私约束（契约4.1）：识别文本仅存 candidates.private_text，随候选过期删除；
原始音频不落库。 buddies 表保存不可变 manifest，撤回仅置标记。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

_LOCAL = threading.local()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_thread_conn(db_path: str) -> sqlite3.Connection:
    """每线程一个连接（线程本地存储），首次调用时创建。

    避免共享连接跨线程事务交错；init_schema 仍只在启动时跑一次。
    """
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        conn = connect(db_path)
        _LOCAL.conn = conn
    return conn


def close_thread_conn() -> None:
    """测试钩子：关闭并清理当前线程的连接，避免跨测试复用指向旧库的连接。"""
    conn = getattr(_LOCAL, "conn", None)
    if conn is not None:
        conn.close()
        del _LOCAL.conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id TEXT PRIMARY KEY,
            content_json TEXT NOT NULL,
            private_text TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS generations (
            generation_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            buddy_id TEXT,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS buddies (
            buddy_id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            content_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            package_size INTEGER NOT NULL,
            published_at TEXT NOT NULL,
            withdrawn INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS counters (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        );
        """
    )
    conn.commit()


def bump_counter(conn: sqlite3.Connection, key: str, delta: int = 1) -> None:
    with conn:
        conn.execute(
            "INSERT INTO counters(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = value + ?",
            (key, delta, delta),
        )


def get_counters(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT key, value FROM counters").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ---------- candidates ----------

def insert_candidate(conn, candidate_id: str, content: dict, private_text: str | None,
                     created_at: str, expires_at: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO candidates(candidate_id, content_json, private_text, created_at, expires_at)"
            " VALUES(?,?,?,?,?)",
            (candidate_id, json.dumps(content, ensure_ascii=False),
             private_text, created_at, expires_at),
        )


def get_candidate(conn, candidate_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)
    ).fetchone()


def delete_expired_candidates(conn, now: str) -> int:
    with conn:
        cur = conn.execute("DELETE FROM candidates WHERE expires_at <= ?", (now,))
        return cur.rowcount


def list_candidates(conn, limit: int = 100) -> list[sqlite3.Row]:
    """后台用：只取元数据，不取 private_text。"""
    return conn.execute(
        "SELECT candidate_id, content_json, created_at, expires_at FROM candidates"
        " ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()


# ---------- generations ----------

def insert_generation(conn, generation_id: str, candidate_id: str, now: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO generations(generation_id, candidate_id, status, created_at, updated_at)"
            " VALUES(?,?, 'pending', ?, ?)",
            (generation_id, candidate_id, now, now),
        )


def get_generation(conn, generation_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM generations WHERE generation_id = ?", (generation_id,)
    ).fetchone()


def get_generation_by_candidate(conn, candidate_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM generations WHERE candidate_id = ?", (candidate_id,)
    ).fetchone()


def update_generation(conn, generation_id: str, status: str,
                      buddy_id: str | None, error_code: str | None) -> None:
    with conn:
        conn.execute(
            "UPDATE generations SET status=?, buddy_id=?, error_code=?, updated_at=?"
            " WHERE generation_id=?",
            (status, buddy_id, error_code, now_iso(), generation_id),
        )


def reset_generation_for_retry(conn, generation_id: str) -> bool:
    """仅当任务当前为 failed 时重置为 pending；返回是否真正重置。

    返回 False 说明状态已被别的请求处理，调用方不应再启动执行线程。
    """
    with conn:
        cur = conn.execute(
            "UPDATE generations SET status='pending', buddy_id=NULL, error_code=NULL,"
            " updated_at=? WHERE generation_id=? AND status='failed'",
            (now_iso(), generation_id),
        )
        return cur.rowcount > 0


def list_generations(conn, limit: int = 100) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM generations ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()


# ---------- buddies ----------

def insert_buddy(conn, buddy_id: str, schema_version: int, content: dict,
                 content_hash: str, manifest: dict, package_size: int,
                 published_at: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO buddies(buddy_id, schema_version, content_json, content_hash,"
            " manifest_json, package_size, published_at, withdrawn)"
            " VALUES(?,?,?,?,?,?,?,0)",
            (buddy_id, schema_version,
             json.dumps(content, ensure_ascii=False), content_hash,
             json.dumps(manifest, ensure_ascii=False), package_size, published_at),
        )


def get_buddy(conn, buddy_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM buddies WHERE buddy_id = ?", (buddy_id,)).fetchone()


def list_buddies_page(conn, limit: int,
                      after: tuple[str, str] | None) -> list[sqlite3.Row]:
    """published_at 降序 + buddy_id 降序的稳定分页。"""
    if after is None:
        return conn.execute(
            "SELECT * FROM buddies WHERE withdrawn = 0"
            " ORDER BY published_at DESC, buddy_id DESC LIMIT ?", (limit,)
        ).fetchall()
    published_at, buddy_id = after
    return conn.execute(
        "SELECT * FROM buddies WHERE withdrawn = 0"
        " AND (published_at < ? OR (published_at = ? AND buddy_id < ?))"
        " ORDER BY published_at DESC, buddy_id DESC LIMIT ?",
        (published_at, published_at, buddy_id, limit),
    ).fetchall()


def withdraw_buddy(conn, buddy_id: str) -> bool:
    with conn:
        cur = conn.execute(
            "UPDATE buddies SET withdrawn = 1 WHERE buddy_id = ? AND withdrawn = 0",
            (buddy_id,),
        )
        return cur.rowcount > 0


def list_buddies_admin(conn, limit: int = 200) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM buddies ORDER BY published_at DESC, buddy_id DESC LIMIT ?",
        (limit,),
    ).fetchall()
