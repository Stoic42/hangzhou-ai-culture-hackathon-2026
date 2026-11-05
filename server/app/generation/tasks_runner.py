"""生成任务后台执行器：在独立线程中生成、校验、发布，并回写任务状态。

使用独立 SQLite 连接（线程安全）；发布与任务成功状态在同一事务提交，
保证契约“任务进入 succeeded 时 buddy_id 必须已能从公共库读取”。
"""

from __future__ import annotations

import json

from .. import db
from ..library.publish import publish_buddy
from ..providers.base import GenerationFailed, GenerationUnavailable
from ..util import new_id


def run_generation(db_path: str, generation_provider, generation_id: str) -> None:
    conn = db.connect(db_path)
    try:
        row = db.get_generation(conn, generation_id)
        if row is None:
            return
        candidate = db.get_candidate(conn, row["candidate_id"])
        if candidate is None:
            db.update_generation(conn, generation_id, "failed", None, "candidate_expired")
            return

        content = json.loads(candidate["content_json"])
        try:
            game, avatar = generation_provider.make_game_and_avatar(content)
        except (GenerationFailed, GenerationUnavailable):
            db.update_generation(conn, generation_id, "failed", None, "generation_failed")
            return
        except Exception:  # noqa: BLE001 — Provider 缺陷不应击穿任务线程
            db.update_generation(conn, generation_id, "failed", None, "generation_failed")
            return

        buddy_id = new_id("bdy")
        ok = publish_buddy(conn, buddy_id, content, game, avatar)
        if not ok:
            db.update_generation(conn, generation_id, "failed", None,
                                 "rule_validation_failed")
            return
        # publish_buddy 内部已提交；任务状态同事务语义靠顺序写保证可读性
        db.update_generation(conn, generation_id, "succeeded", buddy_id, None)
        db.bump_counter(conn, "generations.succeeded")
    finally:
        conn.close()
