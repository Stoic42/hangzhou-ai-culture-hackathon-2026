"""生成任务后台执行器：在独立线程中生成、校验、发布，并回写任务状态。

使用独立 SQLite 连接（线程安全）；发布与任务成功状态在同一事务提交，
保证契约“任务进入 succeeded 时 buddy_id 必须已能从公共库读取”。
任何未预期异常都会把任务状态收敛为 failed，任务不会悬挂。
"""

from __future__ import annotations

import json
import logging

from .. import db
from ..library.publish import publish_buddy
from ..providers.base import GenerationFailed, GenerationUnavailable
from ..util import new_id

logger = logging.getLogger(__name__)


def run_generation(db_path: str, generation_provider, generation_id: str) -> None:
    conn = db.connect(db_path)
    try:
        try:
            row = db.get_generation(conn, generation_id)
            if row is None:
                return
            candidate = db.get_candidate(conn, row["candidate_id"])
            if candidate is None:
                db.update_generation(conn, generation_id, "failed", None,
                                     "candidate_expired")
                return
            # ISO UTC 定宽字符串可直接字典序比较
            if candidate["expires_at"] <= db.now_iso():
                db.update_generation(conn, generation_id, "failed", None,
                                     "candidate_expired")
                return

            content = json.loads(candidate["content_json"])
            try:
                game, avatar = generation_provider.make_game_and_avatar(content)
            except (GenerationFailed, GenerationUnavailable):
                db.update_generation(conn, generation_id, "failed", None,
                                     "generation_failed")
                return
            except Exception:  # noqa: BLE001 — Provider 缺陷不应击穿任务线程
                db.update_generation(conn, generation_id, "failed", None,
                                     "generation_failed")
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
        except Exception:  # noqa: BLE001 — 兜底：任务状态必须收敛，不得悬挂
            logger.exception("生成任务未预期异常: generation_id=%s", generation_id)
            try:
                db.update_generation(conn, generation_id, "failed", None,
                                     "generation_failed")
            except Exception:  # noqa: BLE001 — 连状态都写不回时至少留下日志
                logger.exception("回写任务失败状态也异常: generation_id=%s",
                                 generation_id)
    finally:
        conn.close()
