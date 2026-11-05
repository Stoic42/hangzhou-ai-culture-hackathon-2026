"""内部撤回：仅运维操作，不提供公开或设备端撤回 API（契约 4.3）。

撤回仅置标记，不删除记录，不影响设备已有缓存。
"""

from __future__ import annotations

import sqlite3

from .. import db


def withdraw(conn: sqlite3.Connection, buddy_id: str) -> bool:
    ok = db.withdraw_buddy(conn, buddy_id)
    if ok:
        db.bump_counter(conn, "buddies.withdrawn")
    return ok
